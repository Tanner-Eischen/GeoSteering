"""Keep page navigation distinct from edits within the current workspace."""

import streamlit as st


def reset_scroll_on_navigation(page: str, project_root: str | None) -> None:
    context = (page, project_root)
    if st.session_state.get("_rendered_page_context") == context:
        return
    st.session_state["_rendered_page_context"] = context
    revision = int(st.session_state.get("_page_navigation_revision", 0)) + 1
    st.session_state["_page_navigation_revision"] = revision
    # Streamlit tabs scroll their active tab into view when mounted. Wait for
    # those layout effects, then position the newly selected page at its header.
    # The internal counter ensures the HTML effect reruns on consecutive page
    # changes. No user-provided content is interpolated into executable code.
    st.html(
        f"""<script>
        /* navigation {revision} */
        (() => {{
          requestAnimationFrame(() => requestAnimationFrame(() => {{
            document.getElementById("stMain")?.scrollTo({{top: 0, left: 0, behavior: "instant"}});
          }}));
        }})();
        </script>""",
        unsafe_allow_javascript=True,
    )
