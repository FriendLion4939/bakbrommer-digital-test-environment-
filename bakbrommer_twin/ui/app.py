"""Entry point of the web interface: ``streamlit run bakbrommer_twin/ui/app.py``.

To add a page: write ``ui/pages/<name>.py`` with a ``render()`` function, add
its title to the translation file under ``nav.<name>`` and list it in
``PAGES`` below.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from bakbrommer_twin.ui import i18n, state
from bakbrommer_twin.ui.i18n import t
from bakbrommer_twin.ui.pages import parameters

# (url path, translation key of the title, material icon, render function)
PAGES: tuple[tuple[str, str, str, Callable[[], None]], ...] = (
    ("parameters", "nav.parameters", ":material/tune:", parameters.render),
)


def main() -> None:
    """Configure the app, draw the sidebar and run the selected page."""
    languages = i18n.available_languages()
    chosen = st.session_state.get("language", i18n.get_language())
    i18n.set_language(chosen if chosen in languages else i18n.DEFAULT_LANGUAGE)
    st.set_page_config(page_title=t("app.title"), page_icon="🛵", layout="wide")
    pages = [
        st.Page(render, title=t(title), icon=icon, url_path=path, default=index == 0)
        for index, (path, title, icon, render) in enumerate(PAGES)
    ]
    selected = st.navigation(pages)
    with st.sidebar:
        st.selectbox(t("app.language"), languages, key="language",
                     index=languages.index(i18n.get_language()))
        if not state.working_profile().validated:
            st.warning(t("app.not_validated"))
    selected.run()


main()
