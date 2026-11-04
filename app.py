"""Internal SCAT / SCIMED / YSTT OMR checking portal.

Run: streamlit run app.py
Safe by default: requires password. For each evaluation, photos are sent to the configured Gemini API for a second reading.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from answer_key_utils import CLASSES,CODES,EXAMS,group_rows,read_csv_bytes,load_bundled,to_csv,evaluate,key_string,key_tuple,available_paper_versions
from front_reader import read_front
from gemini_verify import verify
from verification import parse_manual,normalized_name,plan_verification,finalize_review
from rail_fallback import scan_rail_photo
from template_alignment import scan_template_photo
from omr_engine import decode_image,scan_answers,preview_jpeg,GridNotFound
from bubble_sheet import make_bubble_sheet
from storage import Store,DuplicateResult
from sheets_storage import SheetsStore
from result_workflow import save_verified_result, ExistingResultConflict
from pdf_report import generate_result_pdf, result_pdf_filename

st.set_page_config(page_title='Sri Chaitanya | OMR Result Portal V2.0',page_icon='📋',layout='wide')
st.markdown('''<style>
.block-container {max-width:1150px;padding-top:1.5rem}
[data-testid="stFileUploader"] {border-radius:12px}
@media(max-width:640px){.block-container {padding:0.8rem 0.9rem 2rem}}
</style>''',unsafe_allow_html=True)


def secret(name,default=''):
    try:return str(st.secrets.get(name,os.environ.get(name,default)))
    except Exception:return str(os.environ.get(name,default))


def log_in():
    staff_pass=secret('APP_PASSWORD')
    admin_pass=secret('ADMIN_PASSWORD')
    if not staff_pass:
        st.error('App password is not configured. Set APP_PASSWORD in Streamlit secrets or environment variables. See README.md.')
        st.stop()
    if st.session_state.get('role') in ('staff','admin'):
        return st.session_state['role']
    st.title('Sri Chaitanya — OMR Result Portal')
    st.caption('Authorized staff access only')
    with st.form('login'):
        entered=st.text_input('Portal password',type='password')
        go=st.form_submit_button('Sign in',type='primary')
    if go:
        if admin_pass and entered==admin_pass:st.session_state['role']='admin';st.rerun()
        elif entered==staff_pass:st.session_state['role']='staff';st.rerun()
        else:st.error('Incorrect password.')
    st.stop()

role=log_in()

@st.cache_resource
def get_store(url, key, sheet_id, service_account_json):
    if sheet_id.strip():
        return SheetsStore(sheet_id=sheet_id, service_info=json.loads(service_account_json))
    return Store(url=url, key=key)

try:
    service_account = dict(st.secrets.get('gcp_service_account', {}))
except Exception:
    service_account = {}
try:
    store = get_store(
        secret('SUPABASE_URL'), secret('SUPABASE_SERVICE_KEY'),
        secret('GSHEETS_SPREADSHEET_ID'), json.dumps(service_account),
    )
except Exception as exc:
    st.error('Google Sheets connection could not be established. See the setup guide.')
    st.exception(exc)
    st.stop()


def all_keys():
    keys=load_bundled(str(Path(__file__).parent/'answer_keys'))
    for _,data in store.list_keys().items():
        try:
            for k,rows in group_rows(read_csv_bytes(data.encode('utf-8-sig'))).items():keys[k]=rows
        except (ValueError,TypeError):continue
    return keys


def file_input(label,key):
    mode=st.radio(label+' source',['Upload photo','Take photo'],horizontal=True,key=key+'_mode')
    if mode=='Take photo':return st.camera_input('Capture '+label,key=key+'_camera')
    return st.file_uploader('Upload '+label,type=['png','jpg','jpeg'],key=key+'_upload')


def encode_for_gemini(image):
    # Retain sufficient resolution for the small answer circles.
    return preview_jpeg(image,max_width=1600)

st.title('SCAT / SCIMED / YSTT — OMR Results')
st.caption('Internal examination evaluation • automatic quality review')
with st.sidebar:
    st.write('**Signed in as:** '+role.title())
    st.write('**Database:** '+('Google Sheets (persistent)' if getattr(store, 'is_sheets', False) else ('Supabase (persistent)' if store.is_cloud else 'Local SQLite (server disk)')))
    if st.button('Log out'):
        st.session_state.clear();st.rerun()
    st.caption('Original photos are not saved in the database.')
    if role=='admin':
        st.caption('Verification service: '+('Configured' if secret('GEMINI_API_KEY').strip() else 'Not configured'))

tabs=['Evaluate OMR','Saved Results']+(['Answer Key Admin'] if role=='admin' else [])
views=st.tabs(tabs)

# A key was just published on the Admin tab. Apply the new selection BEFORE
# creating Streamlit widgets; setting widget keys after instantiation is unsafe.
pending_key=st.session_state.pop('pending_published_key',None)
if pending_key:
    st.session_state['select_exam_type']=pending_key[0]
    st.session_state['select_present_class']=pending_key[1]
    st.session_state['select_paper_code']=pending_key[2]
    st.session_state['select_paper_version']=pending_key[3]

with views[0]:
    try:keys=all_keys()
    except Exception as e:
        st.error(f'Could not load keys: {e}');st.stop()
    if st.session_state.pop('published_key_notice',False):
        st.success('Answer key published to the database. The exam, class, code and version below have been selected automatically.')

    # These selectors intentionally live OUTSIDE a Streamlit form. Changes to
    # exam, class and paper code refresh the available versions immediately.
    a,b,c=st.columns([1,1,1])
    with a:
        exam=st.selectbox('Exam type',EXAMS,key='select_exam_type')
    with b:
        class_name=st.selectbox('Present class',CLASSES,
                                index=CLASSES.index('10th'),key='select_present_class')
    with c:
        paper_code=st.selectbox('Paper code',CODES,key='select_paper_code')

    available=available_paper_versions(keys,exam,class_name,paper_code)
    if available:
        if st.session_state.get('select_paper_version') not in available:
            # Different classes may have completely different version labels.
            st.session_state['select_paper_version']=available[-1]
        version=st.selectbox('Paper version',available,key='select_paper_version')
    else:
        # Avoid attempting to render a blank version selector.
        st.session_state.pop('select_paper_version',None)
        version='No answer key uploaded'
        st.warning(f'No answer key yet for {exam} / {class_name} / Code {paper_code}. '
                   'An admin must publish one first.')
    event_date=st.date_input('Examination date',value=date.today())
    selected=(exam,class_name,paper_code,version)
    chosen_rows=keys.get(selected)
    if not chosen_rows:
        st.warning('No answer key for this exam/class/paper. An admin must upload its CSV first.')
    else:
        st.info(f'Loaded {len(chosen_rows)} questions • {len(set(r["Subject"] for r in chosen_rows))} subjects • paper {version}')
    x,y=st.columns(2)
    with x:front_photo=file_input('OMR front side','front')
    with y:back_photo=file_input('OMR back side','back')
    rot_left,rot_right=st.columns(2)
    with rot_left:front_rotation=st.selectbox('Rotate front image',['No rotation','90° left','180°','90° right'],key='frontrotation')
    with rot_right:back_rotation=st.selectbox('Rotate back image',['No rotation','90° left','180°','90° right'],key='backrotation')
    rotation={'No rotation':0,'90° left':90,'180°':180,'90° right':270}
    front_bytes=front_photo.getvalue() if front_photo is not None else b''
    back_bytes=back_photo.getvalue() if back_photo is not None else b''
    signature=hashlib.sha256(front_bytes+back_bytes+repr((selected,event_date.isoformat(),front_rotation,back_rotation)).encode()+
                             (to_csv(chosen_rows) if chosen_rows else b'')).hexdigest()
    configured_key=secret('GEMINI_API_KEY').strip()
    if not configured_key and role=='admin':
        st.info('Independent Gemini checking is not configured. Python will evaluate the OMR and uncertain bubbles will require staff confirmation. Set GEMINI_API_KEY in .streamlit/secrets.toml to enable the second check.')

    def _python_read(front_img,back_img,n):
        # Use the existing image-based detection first; fall back to the R8.1
        # timing rail alignment for rotated/faded/poorly lit paper images.
        method='two photo readers'
        regular=None;rails=None
        try:
            regular=scan_answers(back_img,n)
        except (ValueError,GridNotFound):pass
        try:
            rails=scan_rail_photo(back_img,n)
        except (ValueError,GridNotFound):pass
        if regular is None and rails is None:
            # Perspective-aware printed-template matching handles camera photos
            # that do not expose sufficiently straight pink lines or all rail marks.
            found=scan_template_photo(back_img,n)
            details=read_front(front_img)
            return found,details,'printed-template registration (photo fallback)'
        if regular is None:
            found=rails;method='timing rails (fallback)'
        elif rails is None:
            found=regular;method='pink grid (fallback)'
        else:
            # A difference between the two independent Python alignments is
            # never allowed to pass unnoticed, even if Gemini agrees.
            found=regular
            for q in range(1,n+1):
                if regular.answers[q]!=rails.answers[q]:
                    found.answers[q]='UNREADABLE'
                    found.confidence[q]=0.0
        details=read_front(front_img)
        return found,details,method

    if st.button('Evaluate OMR',type='primary',disabled=not(front_bytes and back_bytes and chosen_rows),use_container_width=True):
        st.session_state.pop('active_scan',None)
        st.session_state.pop('finalized_scan',None)
        with st.spinner('Reading and verifying the OMR...'):
            try:
                front_img=decode_image(front_bytes,rotation[front_rotation])
                back_img=decode_image(back_bytes,rotation[back_rotation])
                n=len(chosen_rows)
                # The independent reader runs in parallel when configured. A failed
                # remote request must NEVER prevent a high-confidence Python
                # evaluation, but it must NEVER count as double verification.
                # Python uncertainty still requires staff confirmation.
                bubble_sheet=None
                second=None
                remote_error=None
                if configured_key:
                    try:
                        bubble_sheet=make_bubble_sheet(back_img,n)
                    except Exception as crop_error:
                        # An AI-only image crop failure must not suppress a valid
                        # local OMR evaluation. Record it as a failed second check.
                        remote_error=RuntimeError(
                            f'Independent image preparation failed: {type(crop_error).__name__}'
                        )
                with ThreadPoolExecutor(max_workers=2) as pool:
                    local_job=pool.submit(_python_read,front_img,back_img,n)
                    remote_job=None
                    if configured_key and remote_error is None:
                        try:
                            front_for_ai=encode_for_gemini(front_img)
                            back_for_ai=encode_for_gemini(back_img)
                            remote_job=pool.submit(
                                verify,front_for_ai,back_for_ai,n,configured_key,
                                secret('GEMINI_MODEL','gemini-2.5-flash'),bubble_sheet
                            )
                        except Exception as preparation_error:
                            remote_error=RuntimeError(
                                f'Independent image encoding failed: {type(preparation_error).__name__}'
                            )
                    try:
                        scan,identity,scanner_method=local_job.result()
                    except Exception as local_error:
                        raise RuntimeError(f"Python OMR reader failed: {local_error}") from local_error
                    if remote_job is not None:
                        try:
                            second=remote_job.result()
                        except Exception as error:
                            remote_error=error
                decision=plan_verification(
                    scan.answers,n,scan.confidence,
                    remote_answers=second.get('answers') if second else None,
                    remote_error=remote_error,
                )
                accepted=decision.accepted
                questions=decision.issues
                remote_ok=decision.remote_ok
                remote_note=decision.note
                verification_status=decision.status
                second=second or {}
                st.session_state['active_scan']={
                    'signature':signature,'selected':selected,'date':event_date.isoformat(),
                    'matched_answers':accepted,'issues':questions,
                    'remote_ok':remote_ok,'remote_note':remote_note,
                    'verification_status':verification_status,
                    'bubble_sheet':bubble_sheet,
                    'identity':identity,'back':back_img,'front':front_img,
                    'overlay':scan.preview,'scanner_method':scanner_method,
                    'python_answers':scan.answers,'second_answers':second.get('answers', {}),
                    'second_name':second.get('student_name',''),'second_roll':second.get('roll_number',''),
                    'second_fields':{key:second.get(key,'') for key in (
                        'student_phone','parent_phone','school_name','school_city','gender','exam_center')},
                    'image_hash':hashlib.sha256(front_bytes+back_bytes).hexdigest(),
                }
            except Exception as e:
                # Python scanner and image processing errors are still blocking failures.
                if role=='admin':
                    st.error('Verification could not finish: '+str(e))
                    with st.expander('Diagnostic details (admin only)'):
                        st.code(f'{type(e).__name__}: {e}',language='text')
                else:
                    stage=('Python OMR scanning' if 'Python OMR reader failed:' in str(e) else
                           'image processing or application configuration')
                    st.error(f'The OMR could not be verified ({stage}). Please contact the administrator. No result has been saved.')

    work=st.session_state.get('active_scan')
    if work and (work['signature']!=signature or work['selected']!=selected):
        st.info('OMR photos or examination options changed. Please evaluate again.')
        work=None

    if work:
        st.divider()
        identity=work['identity']
        issues=work['issues']
        suggested=work.get('second_fields',{})
        st.subheader('Review student information')
        st.caption('Information is suggested from the OMR photo; please correct any mistakes. Fields marked optional can be left blank.')

        # One explicit staff confirmation saves the evaluated record before revealing results.
        # In V1.4 selecting an answer was not sufficient to advance because
        # missing roll/name silently gated the entire result section.
        already_saved = bool(st.session_state.get('finalized_scan', {}).get('signature') == signature
                             and st.session_state['finalized_scan'].get('saved')
                             and st.session_state['finalized_scan'].get('payload'))
        if already_saved:
            st.success('This result has already been saved. The PDF and marks are available below.')
        with st.form('finish_review_'+signature,clear_on_submit=False):
            left,right=st.columns(2)
            with left:
                name=st.text_input('Student name',value=identity.name or work['second_name'],
                    key='student_name_'+signature)
                roll=st.text_input('Roll number',value=identity.roll_number or work['second_roll'],
                    key='roll_'+signature,help='Enter exactly as written on the OMR. Leading zeros are preserved.')
                school=st.text_input('School name (optional)',value=suggested.get('school_name',''),key='school_'+signature)
                school_city=st.text_input('School city (optional)',value=suggested.get('school_city',''),key='city_'+signature)
            with right:
                student_phone=st.text_input('Student phone (optional)',value=suggested.get('student_phone',''),key='student_phone_'+signature)
                parent_phone=st.text_input('Parent phone (optional)',value=suggested.get('parent_phone',''),key='parent_phone_'+signature)
                g=suggested.get('gender','').strip().lower()
                gindex={'male':1,'female':2,'other':3}.get(g,0)
                gender=st.selectbox('Gender (optional)', ['Not provided','Male','Female','Other'],
                    index=gindex,key='gender_'+signature)
                center=st.text_input('Exam centre / city (optional)',value=suggested.get('exam_center',''),key='centre_'+signature)
            if identity.alerts:
                st.caption('Some front-side fields were unclear to the local reader. Please check the photo before confirming.')
            identity_mismatch=(bool(identity.name and work['second_name'] and
                    normalized_name(identity.name)!=normalized_name(work['second_name'])) or
                    bool(identity.roll_number and work['second_roll'] and identity.roll_number!=work['second_roll']))
            if identity_mismatch:
                st.warning('The two readers disagree on identity. Confirm the name and roll number from the OMR.')
            selections={}
            if issues:
                st.subheader(f'Please check {len(issues)} answer(s)')
                st.info('Select what is actually marked. "Multiple marked" is a valid confirmation and scores according to the paper rules.')
                for issue in issues:
                    q=issue['question']
                    with st.container(border=True):
                        st.write(f'**Question {q}** — {issue["reason"]}. What answer is marked?')
                        selections[q]=st.selectbox('Marked answer',
                            ['Select answer','A','B','C','D','Unattempted','Multiple marked'],
                            key=f'confirm_{signature}_{q}',label_visibility='collapsed')
            submit_review=st.form_submit_button('Confirm details & save result',type='primary',use_container_width=True,
                                                 disabled=already_saved)

        if submit_review:
            # Staff confirms the OMR once. A successful database write is REQUIRED
            # before any marks or PDF are shown. There is no separate save button.
            try:
                final_answers=finalize_review(work['matched_answers'],issues,selections,len(chosen_rows))
            except ValueError as error:
                st.warning(str(error))
            else:
                if not name.strip() or not roll.strip():
                    st.warning('Please confirm the student name and roll number to save the result. '
                               'Marks and the PDF will appear after saving succeeds.')
                else:
                    calculated=evaluate(final_answers,chosen_rows)
                    if calculated['needs_review']:
                        st.warning('Some answers still need confirmation. Please review them above.')
                    else:
                        payload={
                            'image_hash':work['image_hash'],'exam_date':work['date'],
                            'exam_type':exam,'class_name':class_name,
                            'paper_code':paper_code,'paper_version':version,
                            'roll_number':roll.strip(),'student_name':name.strip(),
                            'total':calculated['total'],'maximum':calculated['maximum'],
                            'verification_status':work['verification_status']+
                                (' + staff review' if issues else ''),
                            'subjects':calculated['subjects'],'answers':final_answers,
                            'question_evaluation':calculated['rows'],
                            'school':school.strip(),'school_city':school_city.strip(),
                            'student_phone':student_phone.strip(),
                            'parent_phone':parent_phone.strip(),
                            'gender':gender,'exam_center':center.strip(),
                            'reviewed_questions':[v['question'] for v in issues],
                        }
                        with st.spinner('Saving verified result to the database...'):
                            try:
                                saved_payload,reused=save_verified_result(store,payload)
                                st.session_state['finalized_scan']={
                                    'signature':signature,
                                    'saved':True,
                                    'payload':saved_payload,
                                    'reused':reused,
                                }
                                st.rerun()
                            except ExistingResultConflict as error:
                                st.error(str(error))
                            except Exception as error:
                                # Do not show an unsaved result or generate its PDF.
                                if role=='admin':
                                    st.error(f'Google Sheets could not save the result: {error}')
                                else:
                                    st.error('The result could not be saved. Please retry or contact the '
                                             'administrator. No new result is being displayed.')

        with st.expander('View original OMR photographs'):
            col1,col2=st.columns(2)
            with col1:st.image(work['front'][:,:,::-1],caption='Front side',use_container_width=True)
            with col2:st.image(work['back'][:,:,::-1],caption='Back side',use_container_width=True)
        if role=='admin':
            with st.expander('Technical diagnostics — administrator only'):
                st.write('Reader:',work['scanner_method'])
                st.write('Verification status:',work['verification_status'])
                if not work['remote_ok']:st.warning(work['remote_note'])
                if work.get('bubble_sheet') is not None:
                    st.image(work['bubble_sheet'],caption='Numbered bubble crops sent to Gemini',use_container_width=True)
                st.write('Review questions:',[v['question'] for v in issues])
                st.image(work['overlay'][:,:,::-1],caption='Detected answer circles',use_container_width=True)
                st.dataframe(pd.DataFrame([{
                    'Question':q,'Local reader':work['python_answers'][q] or '(blank)',
                    'Independent reader':work['second_answers'].get(q, 'UNAVAILABLE') or '(blank)'}
                    for q in range(1,len(chosen_rows)+1)]),hide_index=True,use_container_width=True)

        finalized=st.session_state.get('finalized_scan')
        if finalized and finalized['signature']==signature and finalized.get('saved') and finalized.get('payload'):
            # This section is reachable ONLY after Sheets/SQLite acknowledges
            # the write, or an identical previously saved record is retrieved.
            saved_payload=finalized['payload']
            st.divider()
            if finalized.get('reused'):
                st.info('This OMR was already saved. Showing the existing database result; '
                        'no duplicate row has been created.')
            else:
                st.success('Result saved to the database successfully.')
            st.subheader('Examination Result')
            st.write(f"**Student:** {saved_payload['student_name']}   |   "
                     f"**Roll No:** {saved_payload['roll_number']}   |   "
                     f"**Exam:** {saved_payload['exam_type']}")
            a,b=st.columns(2)
            a.metric('Total marks',f"{saved_payload['total']:g} / {saved_payload['maximum']:g}")
            b.metric('Percentage',f"{100*float(saved_payload['total'])/float(saved_payload['maximum']):.1f}%"
                     if float(saved_payload['maximum']) else '-')
            st.dataframe(pd.DataFrame([
                {'Subject':subject,'Marks':info['marks'],'Out of':info['maximum']}
                for subject,info in saved_payload['subjects'].items()
            ]),hide_index=True,use_container_width=True)
            try:
                report=generate_result_pdf(saved_payload)
                st.download_button('Download Sri Chaitanya Result PDF', data=report,
                                   file_name=result_pdf_filename(saved_payload),
                                   mime='application/pdf',type='primary',use_container_width=True,
                                   key='report_'+signature)
            except Exception as pdf_error:
                if role=='admin':
                    st.error(f'The result was saved, but the PDF could not be created: {pdf_error}')
                else:
                    st.error('The result was saved, but the PDF could not be created. '
                             'Please contact the administrator.')
            if saved_payload.get('question_evaluation'):
                st.download_button('Download detailed checking CSV',
                    data=pd.DataFrame(saved_payload['question_evaluation']).to_csv(index=False).encode('utf-8-sig'),
                    file_name=f"{saved_payload['exam_type']}_{saved_payload['class_name']}_"
                              f"{saved_payload['paper_code']}_result.csv",mime='text/csv')

with views[1]:
    st.subheader('Saved results')
    try:
        saved=store.list_results()
        if saved:
            table=pd.DataFrame(saved)
            st.dataframe(table,hide_index=True,use_container_width=True)
            st.download_button('Export results summary CSV',data=table.to_csv(index=False).encode('utf-8-sig'),file_name='SCAT_results_export.csv',mime='text/csv')
            st.divider()
            st.markdown('**Download a previously saved student result PDF**')
            chosen=st.selectbox('Saved student',saved,
                format_func=lambda r: f"{r.get('student_name','')} | {r.get('roll_number','')} | "
                                      f"{r.get('exam_type','')} | {r.get('exam_date','')}",
                key='saved_pdf_selection')
            if chosen:
                try:
                    stored=store.get_result_by_id(chosen['id'])
                    if stored:
                        st.download_button('Download selected result PDF',
                            data=generate_result_pdf(stored),
                            file_name=result_pdf_filename(stored),mime='application/pdf',
                            use_container_width=True,key='saved_pdf_download')
                    else:
                        st.warning('Selected record could not be loaded from the database.')
                except Exception as error:
                    st.error(f'Could not prepare the saved PDF: {error}')
        else:st.info('No results saved yet.')
    except Exception as e:st.error(f'Could not load saved results: {e}')

if role=='admin':
    with views[2]:
        st.subheader('Answer key management')
        st.caption('Upload a CSV using the supplied template. An existing paper version can be replaced deliberately; use a new version for a new paper.')
        uploaded=st.file_uploader('Upload answer key CSV',type=['csv'],key='upload_admin_csv')
        if uploaded:
            try:
                rows=read_csv_bytes(uploaded.getvalue())
                groups=group_rows(rows)
                st.success(f'CSV format validated: {len(rows)} rows across {len(groups)} paper(s).')
                st.dataframe(pd.DataFrame(rows).head(12),hide_index=True)
                existing_keys=all_keys()
                replacements=[key for key in groups if key in existing_keys]
                additions=[key for key in groups if key not in existing_keys]
                if additions:
                    st.info('Not yet saved: click **Publish answer key** below to add '
                            'the following paper version(s) to Google Sheets: '
                            +', '.join(' / '.join(t) for t in additions))
                if replacements:
                    st.warning('Existing paper version(s) will be replaced: '
                               +', '.join(' / '.join(t) for t in replacements))
                overwrite=True
                if replacements:
                    overwrite=st.checkbox('I confirm that the matching existing key(s) should be replaced.')
                if st.button('Publish answer key',type='primary',disabled=not overwrite):
                    try:
                        for key,subrows in groups.items():
                            store.save_key(key_string(key),to_csv(subrows).decode('utf-8-sig'))
                    except Exception as exc:
                        st.error(f'Answer key was not fully published: {exc}')
                    else:
                        # The evaluation tab renders before the admin tab. Trigger
                        # a rerun to show fresh versions and focus on this upload.
                        st.session_state['pending_published_key']=next(iter(groups))
                        st.session_state['published_key_notice']=True
                        st.rerun()
            except Exception as e:st.error(f'Invalid answer key CSV: {e}')
        st.divider()
        st.markdown('**Available paper versions**')
        k=all_keys()
        st.dataframe(pd.DataFrame([{'Exam':t[0],'Class':t[1],'Code':t[2],'Version':t[3],'Questions':len(rows)} for t,rows in sorted(k.items())]),hide_index=True,use_container_width=True)
        if k:
            kselect=st.selectbox('Download answer key',sorted(k.keys()),format_func=lambda x:' • '.join(x))
            st.download_button('Download selected CSV',data=to_csv(k[kselect]),file_name='_'.join(kselect)+'.csv',mime='text/csv')
        blank=(Path(__file__).parent/'answer_keys'/'Answer_Key_Blank_Template.csv')
        st.download_button('Download blank CSV template',data=blank.read_bytes(),file_name='Answer_Key_Blank_Template.csv',mime='text/csv')
