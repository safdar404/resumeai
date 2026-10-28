from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from src.config import ASSETS_DIR, MAX_CHAT_MESSAGE_CHARS
from src.models.profile import (CAREER_STAGES, Award, CandidateProfile, Certification, Education, Experience,
                                LanguageSkill, Project, Publication, Referee, Volunteer)
from src.security.untrusted import looks_like_injection
from src.security.uploads import check_upload
from src.services import chat_intake
from src.services.extraction import extract_text
from src.ui import state as S
from src.ui.components import badge, progress_bar, step_header
from src.ui.steps.common import nav_buttons

MODES = ["Chat", "Form", "Upload"]


def _lines(text: str) -> list[str]:
    return [l.strip(" •-\t") for l in (text or "").splitlines() if l.strip(" •-\t")]


def _csv(text: str) -> list[str]:
    out = []
    for x in (text or "").replace("\n", ",").split(","):
        x = x.strip()
        if x and x.lower() not in [o.lower() for o in out]:
            out.append(x)
    return out


def _save(p: CandidateProfile, msg: str = "Saved.") -> None:
    S.set_profile(p)
    S.refresh_checks()
    st.toast(msg, icon="✅")


# ------------------------------------------------------------------ chat
def _chat() -> None:
    ss = st.session_state
    if not ss.chat:
        key, q = chat_intake.next_question(S.profile(), ss.asked_counts)
        if key:
            ss.asked_counts[key] = ss.asked_counts.get(key, 0) + 1
            ss.next_field = key
            ss.chat.append({"role": "assistant", "content": "Hi! I'm your resume copilot. I can review your profile, choose a design and generate your files. I'll ask one short question at a time and keep a "
                            "running profile on the right. Type *skip* for anything optional.\n\n" + q})
    st.markdown('<div class="cr-agent-intro"><b>✦ Your resume copilot</b><span>Tell your story · Review facts · Choose a design · Create your resume</span></div>', unsafe_allow_html=True)
    st.caption("AI-assisted extraction and drafting when a provider is enabled; offline guidance otherwise.")
    controls = st.columns(3)
    for col, label, command in zip(controls, ["Review profile", "Explore designs", "Generate resume"], ["/review", "/templates", "/generate"]):
        if col.button(label, key="agent_" + command[1:], width="stretch"):
            ss.agent_queued = command
    if ss.get("agent_trace"):
        with st.expander("Agent actions · last turn", expanded=False):
            for tool_name in ss.agent_trace:
                st.write("→ " + tool_name.replace("_", " ").title())
    box = st.container(height=470, border=True)
    with box:
        for m in ss.chat[-40:]:
            with st.chat_message(m["role"], avatar=str(ASSETS_DIR / "career_agent_logo.png") if m["role"] == "assistant" and (ASSETS_DIR / "career_agent_logo.png").exists() else ("🤖" if m["role"] == "assistant" else None)):
                st.markdown(m["content"])
    msg = st.chat_input("Tell me about your experience, or ask me to review, design or generate your resume…", max_chars=MAX_CHAT_MESSAGE_CHARS, key="chat_in")
    msg = ss.pop("agent_queued", None) or msg
    if ss.results:
        a, b = st.columns(2)
        a.button("Preview resume", on_click=S.goto, args=(6,), width="stretch", key="agent_preview")
        b.button("Download files", on_click=S.goto, args=(8,), width="stretch", key="agent_download")
    if msg:
        ss.chat.append({"role": "user", "content": msg})
        if looks_like_injection(msg):
            S.note("Your message contains text that looks like instructions to the AI. It is treated purely as "
                   "resume data and cannot change the app's rules.", "info")
        from src.agents.career_assistant import handle_action
        with st.spinner("Your resume assistant is working…"):
            service = S.llm_service()
            if service is not None:
                from src.agents.tool_agent import run_resume_agent
                from src.services.llm import LLMError
                try:
                    reply = run_resume_agent(msg, service)
                except LLMError as exc:
                    # Keep partial, already saved facts. Never replace them or
                    # falsely claim generation succeeded after an API error.
                    reply = "AI copilot could not finish this turn. " + exc.user_message() + " Your saved profile is still available."
            else:
                reply = handle_action(msg)
                if reply is None:
                    res = S.run_intake("chat", msg)
                    reply = res.get("assistant_message") or "Saved."
        ss.chat.append({"role": "assistant", "content": reply})
        st.rerun()


# ------------------------------------------------------------------ form
def _form() -> None:
    p = S.profile()
    v = st.session_state.profile_version
    t1, t2, t3, t4, t5 = st.tabs(["Personal", "Experience", "Education & skills", "Projects & more", "Referees"])
    with t1, st.form(f"f_personal_{v}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name *", p.full_name)
        headline = c2.text_input("Professional headline", p.headline, placeholder="e.g. GIS Analyst · Remote Sensing")
        email = c1.text_input("Email *", p.contact.email)
        phone = c2.text_input("Phone", p.contact.phone)
        city = c1.text_input("City", p.contact.city)
        country = c2.text_input("Country", p.contact.country)
        li = c1.text_input("LinkedIn URL", p.contact.linkedin)
        gh = c2.text_input("GitHub URL", p.contact.github)
        pf = c1.text_input("Portfolio / website", p.contact.portfolio)
        stage = c2.selectbox("Career stage", list(CAREER_STAGES), format_func=CAREER_STAGES.get,
                             index=list(CAREER_STAGES).index(p.career_stage))
        summary = st.text_area("Professional summary (optional — leave blank to have one drafted from your facts)",
                               p.summary, height=100)
        st.caption("Not needed: photo, date of birth, ID numbers, religion or marital status.")
        if st.form_submit_button("Save personal details", type="primary"):
            q = p.model_copy(deep=True)
            q.full_name, q.headline, q.summary, q.career_stage = name.strip(), headline.strip(), summary.strip(), stage
            c = q.contact
            c.email, c.phone, c.city, c.country = email.strip(), phone.strip(), city.strip(), country.strip()
            c.linkedin, c.github, c.portfolio = li.strip(), gh.strip(), pf.strip()
            _save(q)
            st.rerun()
    with t2:
        for i, e in enumerate(p.experience):
            with st.expander(f"{e.title or 'Untitled role'} — {e.employer or 'employer?'}", expanded=not e.bullets):
                with st.form(f"f_exp_{i}_{v}"):
                    c1, c2 = st.columns(2)
                    title = c1.text_input("Job title *", e.title)
                    emp = c2.text_input("Employer *", e.employer)
                    loc = c1.text_input("Location", e.location)
                    cur = c2.checkbox("I currently work here", e.current)
                    sd = c1.text_input("Start date", e.start_date, placeholder="Mar 2021")
                    ed = c2.text_input("End date", e.end_date, placeholder="Dec 2023", disabled=False)
                    bl = st.text_area("Achievements / responsibilities (one per line)", "\n".join(e.bullets), height=140)
                    a, b = st.columns(2)
                    if a.form_submit_button("Save role", type="primary"):
                        q = p.model_copy(deep=True)
                        q.experience[i] = Experience(id=e.id, title=title.strip(), employer=emp.strip(), location=loc.strip(),
                                                     start_date=sd.strip(), end_date="" if cur else ed.strip(),
                                                     current=cur, bullets=_lines(bl))
                        _save(q); st.rerun()
                    if b.form_submit_button("Remove role"):
                        q = p.model_copy(deep=True); q.experience.pop(i); _save(q, "Role removed."); st.rerun()
        if st.button("＋ Add a role", key=f"add_exp_{v}"):
            q = p.model_copy(deep=True); q.experience.append(Experience()); S.set_profile(q); st.rerun()
    with t3:
        for i, ed in enumerate(p.education):
            with st.expander(f"{ed.degree or 'Qualification'} — {ed.institution or 'institution?'}", expanded=not ed.institution):
                with st.form(f"f_edu_{i}_{v}"):
                    c1, c2 = st.columns(2)
                    deg = c1.text_input("Qualification *", ed.degree, placeholder="BSc")
                    fos = c2.text_input("Field of study", ed.field_of_study)
                    inst = c1.text_input("Institution *", ed.institution)
                    loc = c2.text_input("Location", ed.location)
                    sd = c1.text_input("Start", ed.start_date); en = c2.text_input("End / expected", ed.end_date)
                    gr = c1.text_input("Grade (optional)", ed.grade)
                    det = st.text_area("Details (optional, one per line)", "\n".join(ed.details), height=70)
                    a, b = st.columns(2)
                    if a.form_submit_button("Save qualification", type="primary"):
                        q = p.model_copy(deep=True)
                        q.education[i] = Education(id=ed.id, degree=deg.strip(), field_of_study=fos.strip(),
                                                   institution=inst.strip(), location=loc.strip(), start_date=sd.strip(),
                                                   end_date=en.strip(), grade=gr.strip(), details=_lines(det))
                        _save(q); st.rerun()
                    if b.form_submit_button("Remove"):
                        q = p.model_copy(deep=True); q.education.pop(i); _save(q, "Removed."); st.rerun()
        if st.button("＋ Add a qualification", key=f"add_edu_{v}"):
            q = p.model_copy(deep=True); q.education.append(Education()); S.set_profile(q); st.rerun()
        with st.form(f"f_skills_{v}"):
            tech = st.text_area("Technical skills & tools (comma-separated)", ", ".join(p.skills.technical), height=80)
            soft = st.text_area("Interpersonal skills (comma-separated)", ", ".join(p.skills.interpersonal), height=60)
            if st.form_submit_button("Save skills", type="primary"):
                q = p.model_copy(deep=True); q.skills.technical, q.skills.interpersonal = _csv(tech), _csv(soft)
                _save(q); st.rerun()
    with t4:
        st.markdown("**Projects**")
        for i, pr in enumerate(p.projects):
            with st.expander(pr.name or "Untitled project"):
                with st.form(f"f_proj_{i}_{v}"):
                    c1, c2 = st.columns(2)
                    nm = c1.text_input("Project name", pr.name); rl = c2.text_input("Your role", pr.role)
                    ds = st.text_input("One-line description", pr.description)
                    bl = st.text_area("Outcomes / details (one per line)", "\n".join(pr.bullets), height=80)
                    tc = c1.text_input("Technologies (comma-separated)", ", ".join(pr.technologies))
                    lk = c2.text_input("Link", pr.link)
                    a, b = st.columns(2)
                    if a.form_submit_button("Save project", type="primary"):
                        q = p.model_copy(deep=True)
                        q.projects[i] = Project(id=pr.id, name=nm.strip(), role=rl.strip(), description=ds.strip(),
                                                bullets=_lines(bl), technologies=_csv(tc), link=lk.strip(),
                                                start_date=pr.start_date, end_date=pr.end_date)
                        _save(q); st.rerun()
                    if b.form_submit_button("Remove"):
                        q = p.model_copy(deep=True); q.projects.pop(i); _save(q, "Removed."); st.rerun()
        if st.button("＋ Add a project", key=f"add_proj_{v}"):
            q = p.model_copy(deep=True); q.projects.append(Project()); S.set_profile(q); st.rerun()
        st.markdown("**Certifications, languages, publications and awards** — edit the tables, then save.")
        c_df = pd.DataFrame([c.model_dump(exclude={"id"}) for c in p.certifications] or
                            [{"name": "", "issuer": "", "date": "", "credential_id": ""}])
        l_df = pd.DataFrame([l.model_dump() for l in p.languages] or [{"language": "", "proficiency": ""}])
        pub_df = pd.DataFrame([x.model_dump(exclude={"id"}) for x in p.publications] or
                              [{"title": "", "authors": "", "venue": "", "year": "", "link": ""}])
        aw_df = pd.DataFrame([x.model_dump(exclude={"id"}) for x in p.awards] or
                             [{"title": "", "issuer": "", "date": "", "description": ""}])
        c_ed = st.data_editor(c_df, num_rows="dynamic", width="stretch", key=f"de_cert_{v}")
        l_ed = st.data_editor(l_df, num_rows="dynamic", width="stretch", key=f"de_lang_{v}")
        pub_ed = st.data_editor(pub_df, num_rows="dynamic", width="stretch", key=f"de_pub_{v}")
        aw_ed = st.data_editor(aw_df, num_rows="dynamic", width="stretch", key=f"de_aw_{v}")
        vol_txt = st.text_area("Volunteering (one per line: Role | Organisation | dates)",
                               "\n".join(" | ".join(x for x in (vv.role, vv.organization,
                                                               f"{vv.start_date} – {vv.end_date}".strip(" –")) if x)
                                         for vv in p.volunteering), height=70, key=f"vol_{v}")
        if st.button("Save tables", type="primary", key=f"save_tables_{v}"):
            def rows(df):
                return [{k: ("" if pd.isna(val) else str(val)).strip() for k, val in r.items()} for r in df.to_dict("records")]
            q = p.model_copy(deep=True)
            q.certifications = [Certification(**r) for r in rows(c_ed) if r.get("name")]
            q.languages = [LanguageSkill(**r) for r in rows(l_ed) if r.get("language")]
            q.publications = [Publication(**r) for r in rows(pub_ed) if r.get("title")]
            q.awards = [Award(**r) for r in rows(aw_ed) if r.get("title")]
            vols = []
            for line in _lines(vol_txt):
                parts = [x.strip() for x in line.split("|")]
                dates = parts[2] if len(parts) > 2 else ""
                sd, _, en = dates.partition("–") if "–" in dates else dates.partition("-")
                old = next((x for x in p.volunteering if x.role == parts[0]), None)
                vols.append(Volunteer(role=parts[0], organization=parts[1] if len(parts) > 1 else "",
                                      start_date=sd.strip(), end_date=en.strip(), bullets=old.bullets if old else []))
            q.volunteering = vols
            _save(q); st.rerun()
    with t5:
        st.caption("References are optional. They are only printed if you include them and confirm each referee agreed.")
        inc = st.toggle("Include references on my resume", p.include_referees, key=f"inc_ref_{v}")
        r_df = pd.DataFrame([r.model_dump() for r in p.referees] or
                            [{"name": "", "title": "", "organization": "", "email": "", "phone": "", "relationship": "",
                              "permission_confirmed": False}])
        r_ed = st.data_editor(r_df, num_rows="dynamic", width="stretch", key=f"de_ref_{v}",
                              column_config={"permission_confirmed": st.column_config.CheckboxColumn("Permission given?")})
        if st.button("Save referees", type="primary", key=f"save_ref_{v}"):
            q = p.model_copy(deep=True)
            q.include_referees = inc
            q.referees = [Referee(**{k: (bool(val) if k == "permission_confirmed" else ("" if pd.isna(val) else str(val)))
                                     for k, val in r.items()}) for r in r_ed.to_dict("records") if str(r.get("name") or "").strip()]
            _save(q); st.rerun()


# ------------------------------------------------------------------ upload
def _upload() -> None:
    st.markdown("Upload a **text-based** PDF, DOCX or TXT resume, or a **CareerRainbow JSON profile** you saved earlier. "
                "Max 5 MB. Scanned images need OCR, which this app does not include.")
    f = st.file_uploader("Resume or profile file", type=["pdf", "docx", "txt", "json"], key="uploader")
    if f is None:
        return
    data = f.getvalue()
    chk = check_upload(f.name, data)
    if not chk.ok:
        st.error(chk.message)
        return
    if chk.kind == "json":
        mode = st.radio("How should this profile be used?", ["Replace my current profile", "Merge into my current profile"],
                        horizontal=True)
    if st.button("Import", type="primary"):
        if chk.kind == "json":
            try:
                raw = json.loads(data.decode("utf-8"))
                prof = CandidateProfile.model_validate(raw.get("profile", raw))
            except (ValidationError, ValueError, UnicodeDecodeError) as exc:
                st.error(f"This JSON file is not a valid CareerRainbow profile ({type(exc).__name__}).")
                return
            if mode.startswith("Replace"):
                S.set_profile(prof)
            else:
                from src.agents.intake import merge_profiles
                S.set_profile(merge_profiles(S.profile(), prof))
            S.refresh_checks()
            S.note("Profile imported.", "success")
            st.rerun()
        res = extract_text(chk.kind, data)
        if not res.ok:
            st.error(res.message)
            return
        for w in res.warnings:
            st.warning(w)
        with st.spinner("Reading your resume…"):
            S.run_intake("document", res.text)
        S.note("Imported. Please review every section — automatic extraction can misread layouts. "
               "Items that could not be matched word-for-word are flagged for confirmation.", "success")
        st.rerun()


# ------------------------------------------------------------------ profile panel
def profile_panel() -> None:
    p = S.profile()
    val = st.session_state.validation or {}
    progress_bar(val.get("completion", 0), "Profile completion")
    secs = val.get("sections", {})
    if secs:
        sym = {"complete": "✓", "partial": "◐", "missing": "○", "skipped": "↷"}
        st.markdown("".join(badge(v, f"{sym.get(v, '')} {k}") for k, v in secs.items()), unsafe_allow_html=True)
        st.caption("Badges: ✓ complete · ◐ partial · ○ missing · ↷ skipped")
    with st.container(border=True):
        st.markdown(f"**{p.full_name or 'Your name'}**  \n{p.headline or p.target.occupation or '—'}")
        st.caption(" · ".join(x for x in (p.contact.email, p.contact.phone,
                                         ", ".join(y for y in (p.contact.city, p.contact.country) if y)) if x) or "No contact details yet")
        if p.experience:
            st.markdown("**Experience**  \n" + "  \n".join(f"• {e.title or '?'} — {e.employer or '?'} ({len(e.bullets)} pts)"
                                                          for e in p.experience))
        if p.education:
            st.markdown("**Education**  \n" + "  \n".join(f"• {e.degree} — {e.institution or '?'}" for e in p.education))
        if p.skills.technical:
            st.markdown("**Skills**  \n" + ", ".join(p.skills.technical[:18]) + ("…" if len(p.skills.technical) > 18 else ""))
    issues = val.get("issues", [])
    if issues:
        with st.expander(f"Needs attention ({len(issues)})", expanded=any(i["blocking"] for i in issues)):
            for i in issues:
                kind = "fail" if i["blocking"] else ("warn" if i["severity"] == "warning" else "info")
                st.markdown(badge(kind, "Required" if i["blocking"] else i["severity"].title()) + " " + i["message"],
                            unsafe_allow_html=True)
    missing = val.get("missing_for_export", [])
    if missing:
        st.caption("Still missing (optional unless marked required): " + ", ".join(missing))


def render() -> None:
    step_header(1, "Add information", "Chat, forms and uploads all update the same profile — switch any time without losing work.")
    S.show_notices()
    if st.session_state.validation is None:
        S.refresh_checks()
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        if "entry_mode_ctl" not in st.session_state:
            st.session_state.entry_mode_ctl = st.session_state.get("entry_mode", "Chat")
        mode = st.segmented_control("Input method", MODES, key="entry_mode_ctl", label_visibility="collapsed")
        st.session_state.entry_mode = mode or "Chat"
        {"Chat": _chat, "Form": _form, "Upload": _upload}[st.session_state.entry_mode]()
    with right:
        st.markdown("##### Your profile")
        profile_panel()
    nav_buttons()
