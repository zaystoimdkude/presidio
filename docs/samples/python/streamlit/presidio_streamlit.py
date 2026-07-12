"""Streamlit app for Presidio."""
import io
import logging
import os
import traceback
from pathlib import Path

import dotenv
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from annotated_text import annotated_text
from streamlit_tags import st_tags

from openai_fake_data_generator import OpenAIParams
from presidio_helpers import (
    get_supported_entities,
    analyze,
    anonymize,
    annotate,
    create_fake_data,
    analyzer_engine,
    extract_text_from_file,
)

st.set_page_config(
    page_title="Presidio demo",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "https://data-privacy-stack.github.io/presidio/",
    },
)

dotenv.load_dotenv()
logger = logging.getLogger("presidio-streamlit")


allow_other_models = os.getenv("ALLOW_OTHER_MODELS", False)


# Sidebar
st.sidebar.header(
    """
PII De-Identification with [Presidio](https://data-privacy-stack.github.io/presidio/)
"""
)


model_help_text = """
    Select which Named Entity Recognition (NER) model to use for PII detection, in parallel to rule-based recognizers.
    Presidio supports multiple NER packages off-the-shelf, such as spaCy, Huggingface, Stanza and Flair,
    as well as services such as Azure AI Language PII.
    """
st_ta_key = st_ta_endpoint = ""

model_list = [
    "spaCy/en_core_web_lg",
    "flair/ner-english-large",
    "HuggingFace/obi/deid_roberta_i2b2",
    "HuggingFace/StanfordAIMI/stanford-deidentifier-base",
    "stanza/en",
    "Azure AI Language",
    "Other",
]
if not allow_other_models:
    model_list.pop()
# Select model
st_model = st.sidebar.selectbox(
    "NER model package",
    model_list,
    index=2,
    help=model_help_text,
)

# Extract model package.
st_model_package = st_model.split("/")[0]

# Remove package prefix (if needed)
st_model = (
    st_model
    if st_model_package.lower() not in ("spacy", "stanza", "huggingface")
    else "/".join(st_model.split("/")[1:])
)

if st_model == "Other":
    st_model_package = st.sidebar.selectbox(
        "NER model OSS package", options=["spaCy", "stanza", "Flair", "HuggingFace"]
    )
    st_model = st.sidebar.text_input(f"NER model name", value="")

if st_model == "Azure AI Language":
    st_ta_key = st.sidebar.text_input(
        f"Azure AI Language key", value=os.getenv("TA_KEY", ""), type="password"
    )
    st_ta_endpoint = st.sidebar.text_input(
        f"Azure AI Language endpoint",
        value=os.getenv("TA_ENDPOINT", default=""),
        help="For more info: https://learn.microsoft.com/en-us/azure/cognitive-services/language-service/personally-identifiable-information/overview",  # noqa: E501
    )

st.sidebar.warning("Note: Models might take some time to download. ")

analyzer_params = (st_model_package, st_model, st_ta_key, st_ta_endpoint)
logger.debug(f"analyzer_params: {analyzer_params}")

st_operator = st.sidebar.selectbox(
    "De-identification approach",
    ["redact", "replace", "synthesize", "highlight", "mask", "hash", "encrypt"],
    index=1,
    help="""
    Select which manipulation to the text is requested after PII has been identified.\n
    - Redact: Completely remove the PII text\n
    - Replace: Replace the PII text with a constant, e.g. <PERSON>\n
    - Synthesize: Replace with fake values (requires an OpenAI key)\n
    - Highlight: Shows the original text with PII highlighted in colors\n
    - Mask: Replaces a requested number of characters with an asterisk (or other mask character)\n
    - Hash: Replaces with the hash of the PII string\n
    - Encrypt: Replaces with an AES encryption of the PII string, allowing the process to be reversed
         """,
)
st_mask_char = "*"
st_number_of_chars = 15
st_encrypt_key = "WmZq4t7w!z%C&F)J"

open_ai_params = None

logger.debug(f"st_operator: {st_operator}")


def set_up_openai_synthesis():
    """Set up the OpenAI API key and model for text synthesis."""

    if os.getenv("OPENAI_TYPE", default="openai") == "Azure":
        openai_api_type = "azure"
        st_openai_api_base = st.sidebar.text_input(
            "Azure OpenAI base URL",
            value=os.getenv("AZURE_OPENAI_ENDPOINT", default=""),
        )
        openai_key = os.getenv("AZURE_OPENAI_KEY", default="")
        st_deployment_id = st.sidebar.text_input(
            "Deployment name", value=os.getenv("AZURE_OPENAI_DEPLOYMENT", default="")
        )
        st_openai_version = st.sidebar.text_input(
            "OpenAI version",
            value=os.getenv("OPENAI_API_VERSION", default="2023-05-15"),
        )
    else:
        openai_api_type = "openai"
        st_openai_version = st_openai_api_base = None
        st_deployment_id = ""
        openai_key = os.getenv("OPENAI_KEY", default="")
    st_openai_key = st.sidebar.text_input(
        "OPENAI_KEY",
        value=openai_key,
        help="See https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key for more info.",
        type="password",
    )
    st_openai_model = st.sidebar.text_input(
        "OpenAI model for text synthesis",
        value=os.getenv("OPENAI_MODEL", default="text-davinci-003"),
        help="See more here: https://platform.openai.com/docs/models/",
    )
    return (
        openai_api_type,
        st_openai_api_base,
        st_deployment_id,
        st_openai_version,
        st_openai_key,
        st_openai_model,
    )


if st_operator == "mask":
    st_number_of_chars = st.sidebar.number_input(
        "number of chars", value=st_number_of_chars, min_value=0, max_value=100
    )
    st_mask_char = st.sidebar.text_input(
        "Mask character", value=st_mask_char, max_chars=1
    )
elif st_operator == "encrypt":
    st_encrypt_key = st.sidebar.text_input("AES key", value=st_encrypt_key)
elif st_operator == "synthesize":
    (
        openai_api_type,
        st_openai_api_base,
        st_deployment_id,
        st_openai_version,
        st_openai_key,
        st_openai_model,
    ) = set_up_openai_synthesis()

    open_ai_params = OpenAIParams(
        openai_key=st_openai_key,
        model=st_openai_model,
        api_base=st_openai_api_base,
        deployment_id=st_deployment_id,
        api_version=st_openai_version,
        api_type=openai_api_type,
    )

st_threshold = st.sidebar.slider(
    label="Acceptance threshold",
    min_value=0.0,
    max_value=1.0,
    value=0.35,
    help="Define the threshold for accepting a detection as PII. See more here: ",
)

st_return_decision_process = st.sidebar.checkbox(
    "Add analysis explanations to findings",
    value=False,
    help="Add the decision process to the output table. "
    "More information can be found here: https://data-privacy-stack.github.io/presidio/analyzer/decision_process/",
)

# Allow and deny lists
st_deny_allow_expander = st.sidebar.expander(
    "Allowlists and denylists",
    expanded=False,
)

with st_deny_allow_expander:
    st_allow_list = st_tags(
        label="Add words to the allowlist", text="Enter word and press enter."
    )
    st.caption(
        "Allowlists contain words that are not considered PII, but are detected as such."
    )

    st_deny_list = st_tags(
        label="Add words to the denylist", text="Enter word and press enter."
    )
    st.caption(
        "Denylists contain words that are considered PII, but are not detected as such."
    )
# Main panel

with st.expander("About this demo", expanded=False):
    st.info(
        """Presidio is an open source customizable framework for PII detection and de-identification.
        \n\n[Code](https://github.com/data-privacy-stack/presidio) | 
        [Tutorial](https://data-privacy-stack.github.io/presidio/tutorial/) | 
        [Installation](https://data-privacy-stack.github.io/presidio/installation/) | 
        [FAQ](https://data-privacy-stack.github.io/presidio/faq/) |
        [Feedback](https://forms.office.com/r/9ufyYjfDaY) |"""
    )

    st.info(
        """
    Use this demo to:
    - Experiment with different off-the-shelf models and NLP packages.
    - Explore the different de-identification options, including redaction, masking, encryption and more.
    - Generate synthetic text with Presidio and OpenAI.
    - Configure allow and deny lists.
    
    This demo website shows some of Presidio's capabilities.
    [Visit our website](https://data-privacy-stack.github.io/presidio) for more info,
    samples and deployment options.    
    """
    )

    st.markdown(
        "[![Pypi Downloads](https://img.shields.io/pypi/dm/presidio-analyzer.svg)](https://img.shields.io/pypi/dm/presidio-analyzer.svg)"
        "[![MIT license](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://opensource.org/licenses/MIT)"
        "![GitHub Repo stars](https://img.shields.io/github/stars/data-privacy-stack/presidio?style=social)"
    )

analyzer_load_state = st.info("Starting Presidio analyzer...")

analyzer_load_state.empty()

# ── Sidebar: Entity selector (shared across both tabs) ─────────────────────────
try:
    st_entities_expander = st.sidebar.expander("Choose entities to look for")
    st_entities = st_entities_expander.multiselect(
        label="Which entities to look for?",
        options=get_supported_entities(*analyzer_params),
        default=list(get_supported_entities(*analyzer_params)),
        help="Limit the list of PII entities detected. "
        "This list is dynamic and based on the NER model and registered recognizers. "
        "More information can be found here: https://data-privacy-stack.github.io/presidio/analyzer/adding_recognizers/",
    )
except Exception as e:
    st.sidebar.error(f"Could not load entities: {e}")
    st_entities = []

# ── Main Tabs ──────────────────────────────────────────────────────────────────
tab_text, tab_file = st.tabs(["📝 Text Input", "📂 File Upload & Masking"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Original text input UI (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_text:
    # Read default text
    with open("demo_text.txt") as f:
        demo_text = f.readlines()

    # Create two columns for before and after
    col1, col2 = st.columns(2)

    # Before:
    col1.subheader("Input")
    st_text = col1.text_area(
        label="Enter text", value="".join(demo_text), height=400, key="text_input"
    )

    try:
        # Before
        analyzer_load_state = st.info("Starting Presidio analyzer...")
        analyzer = analyzer_engine(*analyzer_params)
        analyzer_load_state.empty()

        st_analyze_results = analyze(
            *analyzer_params,
            text=st_text,
            entities=st_entities,
            language="en",
            score_threshold=st_threshold,
            return_decision_process=st_return_decision_process,
            allow_list=st_allow_list,
            deny_list=st_deny_list,
        )

        # After
        if st_operator not in ("highlight", "synthesize"):
            with col2:
                st.subheader("Output")
                st_anonymize_results = anonymize(
                    text=st_text,
                    operator=st_operator,
                    mask_char=st_mask_char,
                    number_of_chars=st_number_of_chars,
                    encrypt_key=st_encrypt_key,
                    analyze_results=st_analyze_results,
                )
                st.text_area(
                    label="De-identified", value=st_anonymize_results.text, height=400
                )
        elif st_operator == "synthesize":
            with col2:
                st.subheader("OpenAI Generated output")
                fake_data = create_fake_data(
                    st_text,
                    st_analyze_results,
                    open_ai_params,
                )
                st.text_area(label="Synthetic data", value=fake_data, height=400)
        else:
            st.subheader("Highlighted")
            annotated_tokens = annotate(text=st_text, analyze_results=st_analyze_results)
            annotated_text(*annotated_tokens)

        # table result
        st.subheader(
            "Findings"
            if not st_return_decision_process
            else "Findings with decision factors"
        )
        if st_analyze_results:
            df = pd.DataFrame.from_records([r.to_dict() for r in st_analyze_results])
            df["text"] = [st_text[res.start : res.end] for res in st_analyze_results]
            df_subset = df[["entity_type", "text", "start", "end", "score"]].rename(
                {
                    "entity_type": "Entity type",
                    "text": "Text",
                    "start": "Start",
                    "end": "End",
                    "score": "Confidence",
                },
                axis=1,
            )
            df_subset["Text"] = [st_text[res.start : res.end] for res in st_analyze_results]
            if st_return_decision_process:
                analysis_explanation_df = pd.DataFrame.from_records(
                    [r.analysis_explanation.to_dict() for r in st_analyze_results]
                )
                df_subset = pd.concat([df_subset, analysis_explanation_df], axis=1)
            st.dataframe(df_subset.reset_index(drop=True), use_container_width=True)
        else:
            st.text("No findings")

    except Exception as e:
        print(e)
        traceback.print_exc()
        st.error(e)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — File Upload & Masking
# ═══════════════════════════════════════════════════════════════════════════════
with tab_file:
    st.subheader("📂 Upload a File for PII Detection & Masking")
    st.caption(
        "Supported formats: **TXT, CSV, PDF, DOCX, XLSX, XLS** · "
        "Max file size: 200 MB · "
        "Uses the same NER model and settings selected in the sidebar."
    )

    uploaded_file = st.file_uploader(
        label="Choose a file",
        type=["txt", "csv", "pdf", "docx", "xlsx", "xls"],
        key="file_uploader",
        help="Upload a file to extract its text and run PII detection & anonymization.",
    )

    if uploaded_file is not None:
        st.info(f"📄 **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

        col_run, col_lang = st.columns([3, 1])
        with col_lang:
            file_language = st.selectbox(
                "Language",
                options=["en", "de", "es", "fr", "it", "pt", "nl"],
                index=0,
                key="file_language",
                help="Language of the document text.",
            )
        with col_run:
            run_btn = st.button(
                "🔍 Analyze & Mask",
                type="primary",
                key="run_file_analysis",
                use_container_width=True,
            )

        if run_btn:
            try:
                # ── Step 1: Extract text from file ──────────────────────────
                with st.spinner("Extracting text from file..."):
                    extracted_text = extract_text_from_file(uploaded_file)

                if not extracted_text.strip():
                    st.warning("⚠️ No readable text found in the file.")
                    st.stop()

                st.success(f"✅ Extracted **{len(extracted_text):,}** characters.")

                # ── Step 2: Analyze (find PII) ───────────────────────────────
                with st.spinner("Running PII analysis..."):
                    file_analyze_results = analyze(
                        *analyzer_params,
                        text=extracted_text,
                        entities=st_entities if st_entities else None,
                        language=file_language,
                        score_threshold=st_threshold,
                        return_decision_process=st_return_decision_process,
                        allow_list=st_allow_list,
                        deny_list=st_deny_list,
                    )

                # ── Step 3: Anonymize (mask PII) ─────────────────────────────
                with st.spinner("Masking PII entities..."):
                    if file_analyze_results:
                        file_anonymize_result = anonymize(
                            text=extracted_text,
                            operator=st_operator if st_operator != "synthesize" else "replace",
                            mask_char=st_mask_char,
                            number_of_chars=st_number_of_chars,
                            encrypt_key=st_encrypt_key,
                            analyze_results=file_analyze_results,
                        )
                        masked_text = file_anonymize_result.text
                    else:
                        masked_text = extracted_text

                # ── Step 4: Display results ───────────────────────────────────
                entity_count = len(file_analyze_results)
                entity_types = list(
                    {r.entity_type: None for r in file_analyze_results}.keys()
                )

                # Summary metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("PII entities found", entity_count)
                m2.metric("Unique entity types", len(entity_types))
                m3.metric("Characters processed", f"{len(extracted_text):,}")

                # Before / After comparison
                fc1, fc2 = st.columns(2)
                with fc1:
                    st.subheader("Original Text")
                    st.text_area(
                        label="Extracted content",
                        value=extracted_text,
                        height=400,
                        key="file_original",
                        disabled=True,
                    )
                with fc2:
                    st.subheader("Masked Text")
                    st.text_area(
                        label="After masking",
                        value=masked_text,
                        height=400,
                        key="file_masked",
                        disabled=True,
                    )

                # ── Step 5: Download masked file ──────────────────────────────
                stem = Path(uploaded_file.name).stem
                out_name = f"{stem}_masked.txt"
                st.download_button(
                    label=f"⬇️ Download masked file ({out_name})",
                    data=masked_text.encode("utf-8"),
                    file_name=out_name,
                    mime="text/plain; charset=utf-8",
                    type="primary",
                    key="download_masked",
                )

                # ── Step 6: Findings table ────────────────────────────────────
                st.subheader(
                    "Findings"
                    if not st_return_decision_process
                    else "Findings with decision factors"
                )
                if file_analyze_results:
                    fdf = pd.DataFrame.from_records(
                        [r.to_dict() for r in file_analyze_results]
                    )
                    fdf["text"] = [
                        extracted_text[r.start : r.end] for r in file_analyze_results
                    ]
                    fdf_subset = fdf[
                        ["entity_type", "text", "start", "end", "score"]
                    ].rename(
                        {
                            "entity_type": "Entity type",
                            "text": "Text",
                            "start": "Start",
                            "end": "End",
                            "score": "Confidence",
                        },
                        axis=1,
                    )
                    if st_return_decision_process:
                        exp_df = pd.DataFrame.from_records(
                            [
                                r.analysis_explanation.to_dict()
                                for r in file_analyze_results
                            ]
                        )
                        fdf_subset = pd.concat([fdf_subset, exp_df], axis=1)
                    st.dataframe(
                        fdf_subset.reset_index(drop=True), use_container_width=True
                    )
                else:
                    st.success("✅ No PII entities detected in this file.")

            except Exception as e:
                traceback.print_exc()
                st.error(f"❌ Error processing file: {e}")
    else:
        st.markdown(
            """
            ### How to use
            1. 📤 **Upload** a file using the button above
            2. ⚙️ Configure the **NER model**, **masking strategy**, and **threshold** in the sidebar
            3. 🔍 Click **Analyze & Mask**
            4. ⬇️ **Download** the masked file

            ---
            **Supported file types:**
            | Format | Extension |
            |--------|-----------|
            | Plain text | `.txt` |
            | CSV spreadsheet | `.csv` |
            | PDF document | `.pdf` |
            | Word document | `.docx` |
            | Excel (new) | `.xlsx` |
            | Excel (legacy) | `.xls` |
            """
        )

components.html(
    """
    <script type="text/javascript">
    (function(c,l,a,r,i,t,y){
        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window, document, "clarity", "script", "h7f8bp42n8");
    </script>
    """
)
