
import json
from pathlib import Path

import streamlit as st
from streamlit_local_storage import LocalStorage


# ============================================================
# 1. APP CONFIGURATION AND FILES
# ============================================================

st.set_page_config(
    page_title="Carolina Degree Planner",
    page_icon="🎓",
    layout="wide",
)

BASE_DIR = Path(__file__).parent

PROGRAMS_FILE = BASE_DIR / "unc_programs.json"
REQUIREMENTS_FILE = BASE_DIR / "degree_requirements.json"
PROGRESS_FILE = BASE_DIR / "student_progress.json"
PLAN_FILE = BASE_DIR / "semester_plan.json"
PROFILE_FILE = BASE_DIR / "degree_profile.json"

STATUSES = ["Not taken", "In progress", "Completed"]

SEMESTERS = [
    "Fall 2025",
    "Spring 2026",
    "Fall 2026",
    "Spring 2027",
    "Fall 2027",
    "Spring 2028",
    "Fall 2028",
    "Spring 2029",
]


# ============================================================
# 2. LOAD AND SAVE JSON FILES
# ============================================================

def load_json(file_path, default):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


# Student data stays in this visitor's Streamlit session, never in shared
# server-side JSON files. Public catalog files remain read-only.
USER_DATA_KEYS = {
    PROGRESS_FILE: "student_progress",
    PLAN_FILE: "semester_plan",
    PROFILE_FILE: "degree_profile",
}

def load_student_data(file_path):
    key = USER_DATA_KEYS.get(file_path, "ideas_in_action_progress")
    if key not in st.session_state:
        st.session_state[key] = {}
    return st.session_state[key]


def save_json(file_path, data):
    # Preserve existing save callbacks without writing any visitor data to disk.
    key = USER_DATA_KEYS.get(file_path)
    if key is None and file_path == IDEAS_PROGRESS_FILE:
        key = "ideas_in_action_progress"
    if key is not None:
        st.session_state[key] = data


# Browser-local storage: one independent planner per browser profile.
# Wait for the asynchronous browser component to respond before rendering
# editable widgets, so an empty initial session cannot overwrite saved work.
BROWSER_STORAGE_KEY = "carolina_degree_planner_progress_v1"
BROWSER_FIELDS = (
    "degree_profile", "student_progress", "semester_plan",
    "ideas_in_action_progress",
)
browser_storage = LocalStorage()
if not st.session_state.get("browser_storage_loaded", False):
    browser_items = browser_storage.getAll(key="carolina_browser_initial_load")
    if not isinstance(browser_items, dict):
        st.info("Loading your saved planner from this browser…")
        st.stop()
    stored_backup = browser_items.get(BROWSER_STORAGE_KEY)
    if isinstance(stored_backup, str):
        try:
            stored_backup = json.loads(stored_backup)
        except json.JSONDecodeError:
            stored_backup = None
    if isinstance(stored_backup, dict) and all(
        isinstance(stored_backup.get(field), dict) for field in BROWSER_FIELDS
    ):
        for field in BROWSER_FIELDS:
            st.session_state[field] = stored_backup[field]
    st.session_state["browser_storage_loaded"] = True
    st.rerun()


def browser_backup():
    return {
        "format": "carolina-degree-planner-v1",
        **{field: st.session_state.get(field, {}) for field in BROWSER_FIELDS},
    }


def sync_browser_backup():
    serialized = json.dumps(browser_backup(), sort_keys=True)
    if serialized != st.session_state.get("browser_last_saved"):
        browser_storage.setItem(
            BROWSER_STORAGE_KEY, serialized, key="carolina_browser_auto_save"
        )
        st.session_state["browser_last_saved"] = serialized


program_data = load_json(PROGRAMS_FILE, [])
requirements = load_json(REQUIREMENTS_FILE, {})
saved_progress = load_student_data(PROGRESS_FILE)
semester_plan = load_student_data(PLAN_FILE)
saved_profile = load_student_data(PROFILE_FILE)

# Load Ideas in Action data once, so both the dashboard and tracker can use it.
IDEAS_FILE = BASE_DIR / "ideas_in_action.json"
IDEAS_PROGRESS_FILE = BASE_DIR / "ideas_in_action_progress.json"
IDEAS_STATUSES = [
    "Not started",
    "In progress",
    "Completed",
    "Needs advising confirmation",
]

try:
    with open(IDEAS_FILE, "r", encoding="utf-8") as file:
        ideas_data = json.load(file)
    if not isinstance(ideas_data, dict):
        ideas_data = {}
except (FileNotFoundError, json.JSONDecodeError, OSError):
    ideas_data = {}

ideas_progress = load_student_data(IDEAS_PROGRESS_FILE)
if not isinstance(ideas_progress, dict):
    ideas_progress = {}

if not isinstance(program_data, list):
    program_data = []

if not isinstance(requirements, dict):
    requirements = {}

if not isinstance(saved_progress, dict):
    saved_progress = {}

if not isinstance(semester_plan, dict):
    semester_plan = {}

if not isinstance(saved_profile, dict):
    saved_profile = {}


# ============================================================
# 3. NORMALIZE THE SEMESTER PLAN
# ============================================================

for semester in SEMESTERS:
    if not isinstance(semester_plan.get(semester), list):
        semester_plan[semester] = []

    cleaned_courses = []

    for code in semester_plan[semester]:
        if isinstance(code, str):
            code = code.strip().upper()

            if code and code not in cleaned_courses:
                cleaned_courses.append(code)

    semester_plan[semester] = cleaned_courses

save_json(PLAN_FILE, semester_plan)


# ============================================================
# 4. BUILD THE COURSE CATALOG FROM REQUIREMENTS
# ============================================================

course_catalog = {}


def add_course(code, title="", credits=None):
    if not isinstance(code, str):
        return

    code = code.strip().upper()

    if not code:
        return

    if code not in course_catalog:
        course_catalog[code] = {
            "title": "",
            "credits": None,
        }

    if title and not course_catalog[code]["title"]:
        course_catalog[code]["title"] = str(title).strip()

    if credits is not None:
        try:
            course_catalog[code]["credits"] = float(credits)
        except (ValueError, TypeError):
            pass


def parse_course_item(item):
    if isinstance(item, str):
        # Course strings may look like "ECON 410" or
        # "ECON 410 - Econometrics".
        parts = item.split(" - ", 1)

        if len(parts) == 2:
            code = parts[0].strip()
            title = parts[1].strip()
        else:
            code = item.strip()
            title = ""

        if code and any(char.isdigit() for char in code):
            add_course(code, title)

    elif isinstance(item, dict):
        code = (
            item.get("code")
            or item.get("course")
            or item.get("course_code")
            or item.get("number")
        )

        title = (
            item.get("title")
            or item.get("name")
            or item.get("course_title")
            or ""
        )

        credits = (
            item.get("credits")
            or item.get("credit_hours")
            or item.get("hours")
        )

        if isinstance(code, str):
            add_course(code, title, credits)


def get_group_items(group):
    """
    Extract course choices from common requirement formats.
    Supports courses, options, choose_one, and alternatives.
    """
    items = []

    for field in ("courses", "options", "choose_one", "alternatives"):
        value = group.get(field, [])

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and not (
                    item.get("code")
                    or item.get("course")
                    or item.get("course_code")
                    or item.get("number")
                ):
                    # Some formats nest course options.
                    nested = (
                        item.get("courses")
                        or item.get("options")
                        or item.get("alternatives")
                    )

                    if isinstance(nested, list):
                        for nested_item in nested:
                            items.append(nested_item)
                    continue

                items.append(item)

        elif isinstance(value, dict):
            items.extend(value.values())

    # Preserve order while removing duplicate entries.
    unique_items = []
    seen = set()

    for item in items:
        marker = json.dumps(item, sort_keys=True, default=str)

        if marker not in seen:
            seen.add(marker)
            unique_items.append(item)

    return unique_items


def normalize_requirement_course(item):
    if isinstance(item, str):
        parts = item.split(" - ", 1)
        code = parts[0].strip().upper()
        title = parts[1].strip() if len(parts) == 2 else ""
        credits = None

    elif isinstance(item, dict):
        code = (
            item.get("code")
            or item.get("course")
            or item.get("course_code")
            or item.get("number")
            or ""
        )

        title = (
            item.get("title")
            or item.get("name")
            or item.get("course_title")
            or ""
        )

        credits = (
            item.get("credits")
            or item.get("credit_hours")
            or item.get("hours")
        )

        if not isinstance(code, str):
            return None

        code = code.strip().upper()

    else:
        return None

    if not code or not any(char.isdigit() for char in code):
        return None

    add_course(code, title, credits)

    catalog_info = course_catalog.get(code, {})

    return (
        code,
        str(title or catalog_info.get("title") or ""),
        credits if credits is not None else catalog_info.get("credits"),
    )


for degree_data in requirements.values():
    if not isinstance(degree_data, dict):
        continue

    groups = degree_data.get("requirements", [])

    if not isinstance(groups, list):
        continue

    for group in groups:
        if not isinstance(group, dict):
            continue

        for item in get_group_items(group):
            normalize_requirement_course(item)


# ============================================================
# 5. COURSE STATUS HELPERS
# ============================================================

def make_status_key(degree, group_index, group_name, item_index, code):
    return (
        f"status::{degree}::{group_index}::"
        f"{group_name}::{item_index}::{code}"
    )


def get_status(code):
    matching_statuses = []

    for key, value in saved_progress.items():
        if not key.startswith("status::"):
            continue

        if key.split("::")[-1].strip().upper() == code.upper():
            if value in STATUSES:
                matching_statuses.append(value)

    if "Completed" in matching_statuses:
        return "Completed"

    if "In progress" in matching_statuses:
        return "In progress"

    return "Not taken"


def save_course_status(key, status):
    saved_progress[key] = status
    save_json(PROGRESS_FILE, saved_progress)


# ============================================================
# 6. APP TITLE
# ============================================================

st.title("🎓 Carolina Degree Planner")

st.write(
    "Plan your UNC-Chapel Hill degree, track your progress, "
    "find courses, and organize your semesters in one place."
)

st.subheader("Save or restore your planner")
st.caption("No account required. Your planner automatically saves in this browser. You can also download a backup to move to another device.")

backup = {
    **browser_backup(),
}

save_col, restore_col = st.columns(2)
with save_col:
    st.download_button(
        "⬇️ Download my progress",
        data=json.dumps(backup, indent=2),
        file_name="carolina_degree_planner_progress.json",
        mime="application/json",
        use_container_width=True,
    )
with restore_col:
    uploaded_backup = st.file_uploader(
        "Restore saved progress (JSON)",
        type=["json"],
        key="progress_backup_upload",
    )
    if uploaded_backup is not None and st.button("Restore this backup", use_container_width=True):
        try:
            if uploaded_backup.size > 2_000_000:
                raise ValueError("Backup is too large (2 MB maximum).")
            restored = json.loads(uploaded_backup.getvalue().decode("utf-8"))
            if not isinstance(restored, dict) or restored.get("format") != "carolina-degree-planner-v1":
                raise ValueError("This isn't a Carolina Degree Planner backup.")
            fields = ("degree_profile", "student_progress", "semester_plan", "ideas_in_action_progress")
            if any(not isinstance(restored.get(field), dict) for field in fields):
                raise ValueError("The backup has missing or invalid progress sections.")
            # Clear old widget state so imported statuses and degree choices display correctly.
            for key in list(st.session_state.keys()):
                if key.startswith(("status::", "ideas_status_widget_")) or key in ("selected_majors", "selected_minors", "advisor_messages"):
                    del st.session_state[key]
            for field in fields:
                st.session_state[field] = restored[field]
            st.session_state["restore_success"] = True
            st.session_state.pop("browser_last_saved", None)
            st.rerun()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            st.error(f"Could not restore backup: {error}")

if st.session_state.pop("restore_success", False):
    st.success("Your saved progress has been restored.")

st.divider()


# ============================================================
# 7. ACADEMIC PROFILE
# ============================================================

st.header("1. My Academic Profile")

major_options = set()
minor_options = set()

for item in program_data:
    if not isinstance(item, dict):
        continue

    name = str(item.get("name", "")).strip()
    program_type = str(item.get("type", "")).strip().lower()

    if not name:
        continue

    if program_type == "major":
        major_options.add(name)
    elif program_type == "minor":
        minor_options.add(name)

for name in requirements:
    if "minor" in name.lower():
        minor_options.add(name)
    else:
        major_options.add(name)

major_options = sorted(major_options)
minor_options = sorted(minor_options)

saved_majors = [
    name for name in saved_profile.get("majors", [])
    if name in major_options
]

saved_minors = [
    name for name in saved_profile.get("minors", [])
    if name in minor_options
]


def save_degree_profile():
    profile = {
        "majors": st.session_state.get("selected_majors", []),
        "minors": st.session_state.get("selected_minors", []),
    }

    save_json(PROFILE_FILE, profile)


col1, col2 = st.columns(2)

with col1:
    st.multiselect(
        "Select your major(s)",
        options=major_options,
        default=saved_majors,
        key="selected_majors",
        on_change=save_degree_profile,
    )

with col2:
    st.multiselect(
        "Select your minor(s)",
        options=minor_options,
        default=saved_minors,
        key="selected_minors",
        on_change=save_degree_profile,
    )

selected_majors = st.session_state.get("selected_majors", [])
selected_minors = st.session_state.get("selected_minors", [])

planning_degrees = list(
    dict.fromkeys(selected_majors + selected_minors)
)

if planning_degrees:
    st.success(
        "Selected programs: " + ", ".join(planning_degrees)
    )
else:
    st.info(
        "Select your major and minor to personalize your planner."
    )

missing_programs = [
    name for name in planning_degrees
    if name not in requirements
]

if missing_programs:
    st.warning(
        "Detailed requirements have not yet been entered for: "
        + ", ".join(missing_programs)
        + ". These programs can be selected, but their progress "
        "tracking and recommendations will be incomplete."
    )


# ============================================================
# OVERALL GRADUATION DASHBOARD
# ============================================================

st.divider()
st.header("Overall Graduation Dashboard")
st.write(
    "A combined snapshot of your selected programs, Ideas in Action, "
    "and planned coursework. This is a planning summary, not an official degree audit."
)

# Count distinct course codes listed under the selected major/minor programs.
selected_course_codes = set()
for selected_degree in planning_degrees:
    selected_data = requirements.get(selected_degree, {})
    if not isinstance(selected_data, dict):
        continue
    selected_groups = selected_data.get("requirements", [])
    if not isinstance(selected_groups, list):
        continue
    for selected_group in selected_groups:
        if not isinstance(selected_group, dict):
            continue
        for selected_item in get_group_items(selected_group):
            parsed_item = normalize_requirement_course(selected_item)
            if parsed_item:
                selected_course_codes.add(parsed_item[0])

completed_course_codes = {
    code for code in selected_course_codes if get_status(code) == "Completed"
}
in_progress_course_codes = {
    code for code in selected_course_codes if get_status(code) == "In progress"
}
planned_course_codes = {
    code for courses in semester_plan.values() for code in courses
}

ideas_requirement_list = []
ideas_section_keys = [
    "first_year_foundations",
    "focus_capacities",
    "reflection_and_integration",
    "other_general_education",
    "university_wide_degree_requirements",
]
for ideas_section_key in ideas_section_keys:
    section_items = ideas_data.get(ideas_section_key, [])
    if isinstance(section_items, list):
        ideas_requirement_list.extend(
            item for item in section_items if isinstance(item, dict)
        )

ideas_completed = 0
ideas_in_progress = 0
ideas_needing_review = 0
for idea in ideas_requirement_list:
    idea_id = idea.get("id", idea.get("name", ""))
    idea_status = ideas_progress.get(f"ideas::{idea_id}", "Not started")
    if idea_status == "Completed":
        ideas_completed += 1
    elif idea_status == "In progress":
        ideas_in_progress += 1
    elif idea_status == "Needs advising confirmation":
        ideas_needing_review += 1

planned_credit_total = sum(
    course_catalog.get(code, {}).get("credits", 0) or 0
    for code in planned_course_codes
)

metric_cols = st.columns(4)
metric_cols[0].metric(
    "Major/minor course options",
    len(selected_course_codes),
    help="Distinct course codes listed in your selected program requirements; options are not the same as required courses.",
)
metric_cols[1].metric(
    "Course options completed",
    f"{len(completed_course_codes)} / {len(selected_course_codes)}",
)
metric_cols[2].metric(
    "Ideas in Action completed",
    f"{ideas_completed} / {len(ideas_requirement_list)}",
)
metric_cols[3].metric(
    "Credits planned",
    f"{planned_credit_total:g}",
)

with st.expander("See more of your combined progress"):
    detail_cols = st.columns(3)
    detail_cols[0].metric("Courses in progress", len(in_progress_course_codes))
    detail_cols[1].metric("Ideas items in progress", ideas_in_progress)
    detail_cols[2].metric("Ideas items needing advising", ideas_needing_review)
    st.caption(
        "A single course may satisfy more than one requirement, but it only counts once "
        "in the planned-credit total. Because course lists can contain alternatives, "
        "the course-option count is not a percentage of graduation requirements fulfilled. "
        "Confirm requirement completion with UNC's official degree audit and advising."
    )


# ============================================================
# VISUAL PROGRESS BREAKDOWN
# ============================================================

st.subheader("Visual progress breakdown")
st.caption(
    "Program bars show the share of listed course OPTIONS marked completed, "
    "not the percentage of degree requirements satisfied. Imported lists "
    "may include electives and alternatives."
)

for degree_name in planning_degrees:
    degree_detail = requirements.get(degree_name, {})
    course_options = set()
    if isinstance(degree_detail, dict):
        for group in degree_detail.get("requirements", []):
            if not isinstance(group, dict):
                continue
            for item in get_group_items(group):
                parsed = normalize_requirement_course(item)
                if parsed:
                    course_options.add(parsed[0])
    done = sum(get_status(code) == "Completed" for code in course_options)
    total = len(course_options)
    st.write(f"**{degree_name}** — {done} of {total} listed course options completed")
    if total:
        st.progress(done / total)
    else:
        st.caption("No trackable course options available for this program.")

if ideas_requirement_list:
    st.write(
        f"**Ideas in Action** — {ideas_completed} of "
        f"{len(ideas_requirement_list)} tracked items marked completed"
    )
    st.progress(ideas_completed / len(ideas_requirement_list))
else:
    st.caption("No Ideas in Action items are available to track.")

# ============================================================
# 12. AI ACADEMIC ADVISOR — GROQ CLOUD
# ============================================================

# Refresh the advisor's context from the current saved degree planner data.
# We send selected program requirements, not the entire catalog.
advisor_degrees = {}
for degree_name in planning_degrees:
    detail = requirements.get(degree_name, {})
    if isinstance(detail, dict):
        advisor_degrees[degree_name] = detail

advisor_context = {
    "selected_programs": planning_degrees,
    "degree_requirements_from_local_files": advisor_degrees,
    "course_progress": saved_progress,
    "ideas_in_action_requirements": ideas_data,
    "ideas_in_action_progress": ideas_progress,
    "four_year_semester_plan": semester_plan,
}

system_prompt = (
    "You are a supportive academic planning assistant for UNC-Chapel Hill students. "
    "Use the student's planner data below to answer questions about course planning, "
    "possible requirement overlaps, and remaining work. "
    "The degree requirements imported from UNC may be incomplete or unverified: "
    "a course appearing in an imported list does NOT establish that it is mandatory. "
    "Do not invent course availability, prerequisites, credit values, degree rules, "
    "or guarantee that a course fulfills a requirement. "
    "When unsure, say so and direct the student to the official UNC catalog "
    "or an academic advisor. Distinguish saved course statuses from assumptions. "
    "Do not modify the student's data. "
    "Here is the local planner context (JSON):\n"
    + json.dumps(advisor_context, ensure_ascii=False, default=str)[:28000]
)

if "advisor_messages" not in st.session_state:
    st.session_state.advisor_messages = []

# Place the advisor in a compact popover aligned to the upper right.
# Unlike a full-page chat, this stays out of the way of the degree planner.
left_space, advisor_corner = st.columns([5, 2])
with advisor_corner:
    with st.popover("💬 AI Academic Advisor", use_container_width=True):
        st.caption("Groq cloud AI · Suggestions are not official UNC advising")
        if st.button("Clear conversation", key="clear_advisor_chat"):
            st.session_state.advisor_messages = []
            st.rerun()

        chat_history = st.container(height=360)
        with chat_history:
            if not st.session_state.advisor_messages:
                st.info("Ask about your courses, requirements, or semester plan.")
            for message in st.session_state.advisor_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        with st.form("advisor_question_form", clear_on_submit=True):
            question = st.text_input("Your question", placeholder="What should I take next semester?")
            send = st.form_submit_button("Send", use_container_width=True)

        if send and question.strip():
            st.session_state.advisor_messages.append(
                {"role": "user", "content": question.strip()}
            )
            with st.spinner("Thinking with Groq..."):
                try:
                    from groq import Groq

                    api_key = st.secrets.get("GROQ_API_KEY")
                    if not api_key:
                        raise ValueError(
                            "GROQ_API_KEY is missing. Add it to .streamlit/secrets.toml "
                            "locally or to Streamlit Community Cloud Secrets when deployed."
                        )

                    client = Groq(api_key=api_key)
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            *st.session_state.advisor_messages[-12:],
                        ],
                        temperature=0.3,
                        max_completion_tokens=1200,
                    )
                    answer = response.choices[0].message.content
                    if not answer:
                        raise ValueError("Groq returned an empty response. Please try again.")
                    st.session_state.advisor_messages.append(
                        {"role": "assistant", "content": answer}
                    )
                    st.rerun()
                except Exception as error:
                    st.session_state.advisor_messages.pop()
                    st.error(f"Groq couldn't respond: {error}")


# ============================================================
# 8. COURSE SEARCH
# ============================================================

st.divider()
st.header("2. Course Search")

search_query = st.text_input(
    "Search by course code or title",
    placeholder="Try ECON 410, calculus, or statistics",
)

if search_query.strip():
    query = search_query.strip().lower()

    search_results = []

    for code, info in sorted(course_catalog.items()):
        title = info.get("title", "")

        if query in code.lower() or query in title.lower():
            search_results.append((code, info))

    if search_results:
        for code, info in search_results[:50]:
            credits = info.get("credits")
            credit_text = (
                f"{credits:g} credits"
                if isinstance(credits, (int, float))
                else "Credits unknown"
            )

            st.markdown(
                f"**{code}** — "
                f"{info.get('title') or 'Title unavailable'} "
                f"({credit_text})"
            )
    else:
        st.info(
            "No matching courses were found in the current "
            "degree requirements catalog."
        )
else:
    st.caption(
        "Enter a course code or keyword to search the courses "
        "currently included in your degree requirements data."
    )


# ============================================================
# 9. DEGREE PROGRESS TRACKER
# ============================================================

st.divider()
st.header("3. Degree Progress Tracker")

if not planning_degrees:
    st.info(
        "Select your major or minor above to see your degree "
        "requirements and track your progress."
    )

else:
    total_items = 0
    completed_items = 0

    for degree in planning_degrees:
        degree_data = requirements.get(degree)

        st.subheader(degree)

        if not isinstance(degree_data, dict):
            st.info(
                "Detailed requirements have not yet been entered "
                "for this program."
            )
            continue

        if degree_data.get("verification_status") == "Unverified automatic import":
            st.warning(
                "Automatically imported catalog course references — NOT a verified "
                "degree requirement checklist. Some listed courses may be electives "
                "or alternatives. Confirm requirements in the official UNC catalog."
            )

        source = degree_data.get("source")

        if source:
            st.markdown(f"[View program requirements]({source})")

        groups = degree_data.get("requirements", [])

        if not isinstance(groups, list):
            st.info("The requirements data needs to be reviewed.")
            continue

        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue

            group_name = group.get("name", "Requirement")
            description = group.get("description", "")
            items = get_group_items(group)

            with st.expander(group_name, expanded=True):
                if description:
                    st.write(description)

                if not items:
                    st.caption(
                        "This requirement is descriptive. "
                        "Its completion must be verified manually."
                    )
                    continue

                for item_index, item in enumerate(items):
                    parsed = normalize_requirement_course(item)

                    if parsed is None:
                        continue

                    code, title, credits = parsed

                    key = make_status_key(
                        degree,
                        group_index,
                        group_name,
                        item_index,
                        code,
                    )

                    default_status = saved_progress.get(
                        key, get_status(code)
                    )

                    if default_status not in STATUSES:
                        default_status = "Not taken"

                    # Use a stable widget key and persist every change.
                    if key not in st.session_state:
                        st.session_state[key] = default_status

                    def make_status_callback(status_key):
                        def callback():
                            save_course_status(
                                status_key,
                                st.session_state[status_key],
                            )
                        return callback

                    label = f"{code}"

                    if title:
                        label += f" — {title}"

                    if isinstance(credits, (int, float)):
                        label += f" ({credits:g} credits)"

                    st.selectbox(
                        label,
                        options=STATUSES,
                        key=key,
                        on_change=make_status_callback(key),
                    )

                    status = st.session_state[key]
                    saved_progress[key] = status

                    total_items += 1

                    if status == "Completed":
                        completed_items += 1

    save_json(PROGRESS_FILE, saved_progress)

    if total_items:
        percentage = completed_items / total_items

        st.subheader("Overall tracked progress")
        st.progress(percentage)

        st.write(
            f"**{completed_items} of {total_items}** tracked "
            f"course choices marked completed "
            f"({percentage:.0%})."
        )

    else:
        st.info(
            "No individual course choices are available to track "
            "in the selected programs yet."
        )

# --------------------------------------------------
# SECTION 6: IDEAS IN ACTION AND UNIVERSITY REQUIREMENTS
# --------------------------------------------------

st.header("6. Ideas in Action & University Requirements")

st.write(
    "Track your general education and university-wide graduation "
    "requirements separately from your major and minor requirements."
)

if not ideas_data:
    st.error(
        "Ideas in Action requirements could not be loaded. Check that "
        "ideas_in_action.json exists and contains valid JSON."
    )


def save_ideas_progress():
    save_json(IDEAS_PROGRESS_FILE, ideas_progress)


if not ideas_data:
    st.error(
        "The Ideas in Action requirements file could not be loaded. "
        "Check that ideas_in_action.json is in your project folder."
    )
else:
    st.info(
        "Important: This is a planning tracker, not an official degree audit. "
        "Confirm course eligibility and your entry-year requirements "
        "in UNC's catalog and Tar Heel Tracker."
    )

    requirement_sections = [
        ("First-Year Foundations", "first_year_foundations"),
        ("Ideas in Action: Focus Capacities", "focus_capacities"),
        ("Ideas in Action: Reflection and Integration",
         "reflection_and_integration"),
        ("Other General Education", "other_general_education"),
        ("University-Wide Graduation Requirements",
         "university_wide_degree_requirements")
    ]

    total_requirements = 0
    completed_requirements = 0

    for section_title, section_key in requirement_sections:
        section_requirements = ideas_data.get(section_key, [])

        if not section_requirements:
            continue

        st.subheader(section_title)

        for requirement in section_requirements:
            requirement_id = requirement.get("id", requirement.get("name", ""))
            requirement_name = requirement.get("name", "Unnamed requirement")
            progress_key = f"ideas::{requirement_id}"

            saved_status = ideas_progress.get(
                progress_key,
                "Not started"
            )

            if saved_status not in IDEAS_STATUSES:
                saved_status = "Not started"

            with st.container(border=True):
                st.markdown(f"**{requirement_name}**")

                if requirement.get("description"):
                    st.write(requirement["description"])

                if requirement.get("notes"):
                    st.caption(requirement["notes"])

                if requirement.get("minimum_credits") is not None:
                    st.write(
                        f"Minimum credits: "
                        f"{requirement['minimum_credits']}"
                    )

                if requirement.get("minimum_gpa") is not None:
                    st.write(
                        f"Minimum GPA: "
                        f"{requirement['minimum_gpa']:.2f}"
                    )

                eligible_courses = requirement.get("courses", [])

                if eligible_courses:
                    st.caption(
                        "Listed course options: "
                        + ", ".join(eligible_courses)
                    )
                elif requirement.get("type") in [
                    "course_requirement",
                    "focus_capacity",
                    "reflection_integration",
                    "general_education"
                ]:
                    st.caption(
                        "Approved course options still need to be verified."
                    )

                new_status = st.selectbox(
                    "Requirement status",
                    options=IDEAS_STATUSES,
                    index=IDEAS_STATUSES.index(saved_status),
                    key=f"ideas_status_widget_{requirement_id}"
                )

                if new_status != saved_status:
                    ideas_progress[progress_key] = new_status
                    save_ideas_progress()

                total_requirements += 1

                if new_status == "Completed":
                    completed_requirements += 1

    st.divider()
    st.subheader("General Education Progress")

    if total_requirements > 0:
        progress_fraction = completed_requirements / total_requirements

        st.progress(progress_fraction)

        col1, col2 = st.columns(2)

        col1.metric(
            "Requirements marked completed",
            f"{completed_requirements} / {total_requirements}"
        )

        col2.metric(
            "Remaining to review",
            total_requirements - completed_requirements
        )

    st.caption(
        "Your selections are saved separately in "
        "ideas_in_action_progress.json. Mark a requirement completed "
        "only after confirming that you have fulfilled it."
    )

    st.markdown(
        "[View UNC Ideas in Action requirements]"
        "(https://catalog.unc.edu/undergraduate/ideas-in-action/)"
    )

    st.markdown(
        "[View UNC undergraduate degree requirements]"
        "(https://catalog.unc.edu/undergraduate/degree-requirements/)"
    )


# ============================================================
# COURSE OVERLAP AND DOUBLE-COUNTING CHECK
# ============================================================

st.divider()
st.header("Course Overlap & Double-Counting")
st.write(
    "Find courses listed in more than one selected program, or in both "
    "a selected program and an explicitly listed Ideas in Action requirement."
)

# Each course is indexed once, regardless of how many requirements mention it.
program_course_matches = {}
for overlap_degree in planning_degrees:
    overlap_data = requirements.get(overlap_degree, {})
    if not isinstance(overlap_data, dict):
        continue
    overlap_groups = overlap_data.get("requirements", [])
    if not isinstance(overlap_groups, list):
        continue
    for overlap_group in overlap_groups:
        if not isinstance(overlap_group, dict):
            continue
        overlap_group_name = str(overlap_group.get("name", "Requirement"))
        for overlap_item in get_group_items(overlap_group):
            overlap_parsed = normalize_requirement_course(overlap_item)
            if overlap_parsed is None:
                continue
            overlap_code = overlap_parsed[0]
            program_course_matches.setdefault(overlap_code, {}).setdefault(
                overlap_degree, set()
            ).add(overlap_group_name)

ideas_course_matches = {}
ideas_sections_with_unlisted_options = []
for overlap_section_key in ideas_section_keys:
    overlap_section = ideas_data.get(overlap_section_key, [])
    if not isinstance(overlap_section, list):
        continue
    for overlap_idea in overlap_section:
        if not isinstance(overlap_idea, dict):
            continue
        overlap_idea_name = str(overlap_idea.get("name", "Requirement"))
        overlap_idea_courses = overlap_idea.get("courses", [])
        if not isinstance(overlap_idea_courses, list):
            continue
        if not overlap_idea_courses and overlap_idea.get("type") in (
            "course_requirement", "focus_capacity", "reflection_integration",
            "general_education"
        ):
            ideas_sections_with_unlisted_options.append(overlap_idea_name)
        for overlap_item in overlap_idea_courses:
            overlap_parsed = normalize_requirement_course(overlap_item)
            if overlap_parsed is None:
                continue
            ideas_course_matches.setdefault(overlap_parsed[0], set()).add(
                overlap_idea_name
            )

overlap_rows = []
for overlap_code, overlap_programs in sorted(program_course_matches.items()):
    overlap_ideas = sorted(ideas_course_matches.get(overlap_code, set()))
    if len(overlap_programs) < 2 and not overlap_ideas:
        continue
    overlap_rows.append({
        "Course": overlap_code,
        "Programs": "; ".join(sorted(overlap_programs)),
        "Program requirements": "; ".join(
            f"{program}: {', '.join(sorted(group_names))}"
            for program, group_names in sorted(overlap_programs.items())
        ),
        "Ideas in Action matches": "; ".join(overlap_ideas) or "None explicitly listed",
        "Status": get_status(overlap_code),
        "In four-year plan": "Yes" if overlap_code in planned_course_codes else "No",
    })

if not planning_degrees:
    st.info("Select your majors and minors in My Academic Profile to check overlaps.")
elif overlap_rows:
    st.metric("Potential overlapping courses", len(overlap_rows))
    st.dataframe(overlap_rows, use_container_width=True, hide_index=True)
    st.caption(
        "These are matches between course codes in your uploaded requirement files, "
        "not a guarantee that UNC permits the same course to fulfill every listed "
        "requirement. Courses shown as options may not all be required."
    )
else:
    st.info(
        "No course-code overlaps were found among the explicitly listed options "
        "for your selected programs and Ideas in Action requirements."
    )

if ideas_sections_with_unlisted_options:
    with st.expander("Ideas in Action categories needing course eligibility data"):
        st.write(
            "These requirements do not list approved courses in your JSON file, "
            "so the overlap check cannot determine whether your classes satisfy them."
        )
        for overlap_name in ideas_sections_with_unlisted_options:
            st.write("• " + overlap_name)

# Flag a course accidentally appearing in multiple semesters; credits still count once.
planned_course_semesters = {}
for overlap_semester in SEMESTERS:
    for overlap_code in semester_plan.get(overlap_semester, []):
        planned_course_semesters.setdefault(overlap_code, []).append(overlap_semester)
duplicate_planned_courses = {
    code: semesters for code, semesters in planned_course_semesters.items()
    if len(semesters) > 1
}
if duplicate_planned_courses:
    st.warning("Some courses appear in multiple semesters. Check your four-year plan:")
    for overlap_code, overlap_semesters in sorted(duplicate_planned_courses.items()):
        st.write(f"**{overlap_code}:** {', '.join(overlap_semesters)}")

st.caption(
    "A course earns its credit hours once even if it may satisfy multiple "
    "requirements. Confirm double-counting policies and eligibility with "
    "UNC advising or Tar Heel Tracker."
)


# ============================================================
# 11. FOUR-YEAR CLASS PLANNER
# ============================================================

st.divider()
st.header("5. Four-Year Class Planner")

all_planned_courses = {
    code
    for semester in SEMESTERS
    for code in semester_plan[semester]
}

available_codes = [
    code
    for code in sorted(course_catalog)
    if code not in all_planned_courses
]

st.subheader("Add a course to your plan")

with st.form("add_planned_course_form"):
    chosen_semester = st.selectbox(
        "Choose a semester",
        SEMESTERS,
        index=(
            SEMESTERS.index("Spring 2027")
            if "Spring 2027" in SEMESTERS
            else 0
        ),
    )

    if available_codes:
        chosen_course = st.selectbox(
            "Choose a course",
            available_codes,
            format_func=lambda code: (
                f"{code} — "
                f"{course_catalog[code].get('title') or 'Title unavailable'}"
            ),
        )
    else:
        chosen_course = None
        st.info(
            "All courses in the current catalog are already "
            "included in your semester plan."
        )

    add_clicked = st.form_submit_button(
        "Add course to semester",
        disabled=not available_codes,
    )

    if add_clicked and chosen_course:
        semester_plan[chosen_semester].append(chosen_course)
        save_json(PLAN_FILE, semester_plan)

        st.success(
            f"Added {chosen_course} to {chosen_semester}."
        )

        st.rerun()


# ------------------------------------------------------------
# Semester schedule and workload warnings
# ------------------------------------------------------------

st.subheader("Your semester schedule")

total_planned_credits = 0

for semester in SEMESTERS:
    courses = semester_plan[semester]

    semester_credits = sum(
        course_catalog.get(code, {}).get("credits", 0) or 0
        for code in courses
    )


    with st.expander(
        f"{semester} — {len(courses)} course(s), "
        f"{semester_credits:g} known credits",
        expanded=bool(courses),
    ):
        if semester_credits > 18:
            st.warning(
                f"This semester has {semester_credits:g} credits. "
                "Check whether this workload is manageable."
            )

        elif 0 < semester_credits < 12:
            st.info(
                f"This semester has {semester_credits:g} credits. "
                "Check your full-time enrollment requirements."
            )

        if not courses:
            st.caption("No courses planned for this semester yet.")

        for code in list(courses):
            info = course_catalog.get(code, {})
            title = info.get("title", "")
            credits = info.get("credits")

            label = f"**{code}**"

            if title:
                label += f" — {title}"

            if isinstance(credits, (int, float)):
                label += f" · {credits:g} credits"
            else:
                label += " · Credits unknown"

            col1, col2 = st.columns([5, 1])

            with col1:
                st.markdown(label)

            with col2:
                if st.button(
                    "Remove",
                    key=f"remove_{semester}_{code}",
                ):
                    semester_plan[semester].remove(code)
                    save_json(PLAN_FILE, semester_plan)
                    st.rerun()


# ------------------------------------------------------------
# Total credits and academic-year summaries
# ------------------------------------------------------------

st.divider()

total_planned_credits = sum(
    course_catalog.get(code, {}).get("credits", 0) or 0
    for code in all_planned_courses
)
st.metric(
    "Total known planned credits",
    f"{total_planned_credits:g}",
)

st.subheader("Credits by Academic Year")

academic_years = {
    "2025–2026": ["Fall 2025", "Spring 2026"],
    "2026–2027": ["Fall 2026", "Spring 2027"],
    "2027–2028": ["Fall 2027", "Spring 2028"],
    "2028–2029": ["Fall 2028", "Spring 2029"],
}

year_columns = st.columns(4)

for column, (year, semesters) in zip(
    year_columns, academic_years.items()
):
    year_credits = sum(
        course_catalog.get(code, {}).get("credits", 0) or 0
        for semester in semesters
        for code in semester_plan.get(semester, [])
    )

    with column:
        st.metric(year, f"{year_credits:g} credits")


# ============================================================
# 12. FOOTER
# ============================================================

st.divider()

st.caption(
    "Carolina Degree Planner | Your profile, course progress, "
    "and semester plan are saved in your browser (not shared server files)."
)

st.caption(
    "Credit totals include only courses with known credit values. "
    "Workload warnings are general planning guidance, not official "
    "UNC enrollment rules. Always confirm degree requirements and "
    "course availability with UNC-Chapel Hill."
)




# Sync after all widgets have had a chance to update session data.
sync_browser_backup()
