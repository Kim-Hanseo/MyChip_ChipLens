"""ChipLens Streamlit UI (dashboard-agent).

Entry point: ``streamlit run app_streamlit/app.py``. Only this package imports streamlit/plotly;
``core`` stays UI-free. Pure helpers (figures, viewmodel, request_builder) have no streamlit import
so they can be unit-tested and reused in the connection stage.
"""
