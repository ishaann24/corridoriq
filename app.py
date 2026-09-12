import os
import json
import streamlit as st
from data_loader import load_all
from scoring_engine import rank_corridors, get_corridor_summary

try:
    from groq import Groq
except ImportError:
    Groq = None

# Page configuration
st.set_page_config(
    page_title="CorridorIQ — Site Selection & Opportunity Engine",
    page_icon="📍",
    layout="wide"
)

# Cache dataset loading
@st.cache_data
def get_dataset():
    return load_all()

dataset = get_dataset()

def _fallback_explanation(res: dict) -> str:
    strengths_text = " ".join(res.get("strengths", []))
    concerns_text = " ".join(res.get("concerns", []))
    summary = f"{strengths_text} {concerns_text}".strip()
    if not summary:
        summary = f"Corridor {res.get('corridor_name', '')} has an opportunity score of {res.get('opportunity_score', 0)}/100."
    return summary

def get_groq_explanation(res: dict) -> str:
    # Remove internal keys like corridor_id
    evidence = {k: v for k, v in res.items() if k not in ["corridor_id", "metro_id"]}
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            api_key = None
            
    if not api_key or Groq is None:
        return _fallback_explanation(res)
        
    try:
        client = Groq(api_key=api_key)
        system_msg = (
            "You are explaining a commercial corridor recommendation using only the JSON evidence given. "
            "Never invent numbers, places, or facts not present in the evidence. Write 2-3 sentences. "
            "Never claim the business will definitely succeed — describe it as an opportunity signal, "
            "using language like 'shows strong signals for' rather than 'will succeed.'"
        )
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(evidence)}
            ],
            temperature=0.3,
            max_tokens=200
        )
        explanation = completion.choices[0].message.content.strip()
        if explanation:
            return explanation
        return _fallback_explanation(res)
    except Exception:
        return _fallback_explanation(res)

# Title and fixed caption at top of page
st.title("📍 CorridorIQ")
st.caption(
    "Opportunity scores are relative indicators built from relative audience relevance, "
    "activity, fit, and anchor signals in the dataset — not guarantees of foot traffic, revenue, or business success."
)

st.markdown("---")

# Controls section
col1, col2, col3, col4 = st.columns(4)

with col1:
    region = st.selectbox(
        "Select Region",
        options=["nyc", "dallas-fort-worth"],
        format_func=lambda x: "New York City" if x == "nyc" else "Dallas–Fort Worth"
    )

with col2:
    archetypes = dataset["archetypes"].get(region, [])
    archetype_map = {a["archetype_id"]: a["name"] for a in archetypes}
    archetype_id = st.selectbox(
        "Select Business Format",
        options=list(archetype_map.keys()),
        format_func=lambda x: archetype_map.get(x, x)
    )

with col3:
    audience_segments = dataset["audience_segments"]
    audience_map = {s["segment_id"]: s["label"] for s in audience_segments}
    segment_id = st.selectbox(
        "Select Audience",
        options=list(audience_map.keys()),
        format_func=lambda x: audience_map.get(x, x)
    )

with col4:
    period_options = {
        "Morning": "morning",
        "Afternoon": "afternoon",
        "Evening": "evening",
        "Night": "night"
    }
    period_display = st.selectbox(
        "Select Period",
        options=list(period_options.keys())
    )
    period = period_options[period_display]

st.markdown("<br>", unsafe_allow_html=True)
find_button = st.button("Find Opportunities", type="primary", use_container_width=True)

if find_button:
    st.session_state["results"] = rank_corridors(
        dataset=dataset,
        metro_id=region,
        archetype_id=archetype_id,
        audience_segment_id=segment_id,
        period=period,
        top_k=5
    )
    # Clear previous expander states on a new search
    for k in list(st.session_state.keys()):
        if k.startswith("expanded_") or k.startswith("explain_output_"):
            del st.session_state[k]

if "results" in st.session_state:
    results = st.session_state["results"]
    if not results:
        st.warning("No opportunities found for the selected parameters.")
    else:
        st.subheader(f"Top 5 Opportunities for {archetype_map.get(archetype_id, archetype_id)}")
        
        for res in results:
            title = f"{res['opportunity_score']} — {res['corridor_name']}"
            exp_state_key = f"expanded_{res['corridor_id']}"
            is_expanded = st.session_state.get(exp_state_key, False)
            
            with st.expander(title, expanded=is_expanded):
                # Overview metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Opportunity Score", f"{res['opportunity_score']} / 100")
                m2.metric("Fit Tier", res['fit_tier'])
                m3.metric("Audience Score", f"{res['audience_score_raw']} / 10")
                m4.metric("Activity Score", f"{res['activity_score']} / 100")

                st.markdown("---")

                # Details: Strengths and Concerns
                c_left, c_right = st.columns(2)

                with c_left:
                    st.markdown("#### **Strengths**")
                    if res["strengths"]:
                        for s in res["strengths"]:
                            st.markdown(f"<div style='color: #15803d; font-weight: 500;'>• {s}</div>", unsafe_allow_html=True)
                    else:
                        st.write("No specific strengths noted.")

                with c_right:
                    st.markdown("#### **Concerns**")
                    if res["concerns"]:
                        for c in res["concerns"]:
                            st.markdown(f"<div style='color: #c2410c; font-weight: 500;'>• {c}</div>", unsafe_allow_html=True)
                    else:
                        st.write("No specific concerns noted.")

                st.markdown("---")

                # Anchors list
                st.markdown("#### **Anchors & Special Zones**")
                if res["anchors"]:
                    for anchor in res["anchors"]:
                        anchor_name = anchor.get("name", "Unknown Anchor")
                        anchor_class = anchor.get("class", "General")
                        st.markdown(f"• **{anchor_name}** (`{anchor_class}`)")
                else:
                    st.write("No anchor or special zone data available for this corridor.")

                st.markdown("---")

                # Explain button and output container
                exp_key = f"explain_output_{res['corridor_id']}"
                btn_key = f"btn_explain_{res['corridor_id']}"

                if st.button("Explain this recommendation", key=btn_key):
                    st.session_state[exp_key] = get_groq_explanation(res)
                    st.session_state[exp_state_key] = True
                    st.rerun()

                if exp_key in st.session_state:
                    st.info(st.session_state[exp_key])

# --- Ask CorridorIQ Section ---
st.markdown("---")
st.subheader("Ask CorridorIQ")

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "rank_corridors",
            "description": "Rank top 5 commercial corridors for a metro region, business archetype, audience segment, and period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Metro region ID, either 'nyc' or 'dallas-fort-worth'."
                    },
                    "archetype_id": {
                        "type": "string",
                        "description": "Business archetype ID, e.g. 'us.cafe.neighborhood_seated.v1'."
                    },
                    "audience_segment_id": {
                        "type": "string",
                        "description": "Audience segment ID, e.g. 'morning_commuters', 'young_professionals'."
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period: 'morning', 'afternoon', 'evening', or 'night'."
                    }
                },
                "required": ["region", "archetype_id", "audience_segment_id", "period"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_corridor_summary",
            "description": "Get detailed score breakdown and summary for a specific corridor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "corridor_id": {
                        "type": "string",
                        "description": "Unique identifier of the corridor."
                    },
                    "archetype_id": {
                        "type": "string",
                        "description": "Business archetype ID."
                    },
                    "audience_segment_id": {
                        "type": "string",
                        "description": "Audience segment ID."
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period: 'morning', 'afternoon', 'evening', or 'night'."
                    }
                },
                "required": ["corridor_id", "archetype_id", "audience_segment_id", "period"]
            }
        }
    }
]

ask_query = st.text_input("Ask a question about corridors", key="ask_corridoriq_input")
ask_submit = st.button("Submit Question", key="ask_corridoriq_submit")

if ask_submit and ask_query:
    try:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            try:
                api_key = st.secrets.get("GROQ_API_KEY")
            except Exception:
                api_key = None

        if not api_key or Groq is None:
            st.error("Groq API key is missing or groq package is not available.")
        else:
            client = Groq(api_key=api_key)
            system_prompt = (
                "You help answer questions about NYC and Dallas-Fort Worth commercial corridors. "
                "Use the tools to fetch real data before answering. Never invent corridor names, scores, or facts. "
                "If you don't have enough information from the user's question to call a tool "
                "(missing region, business type, audience, or time period), ask a clarifying question instead of guessing."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ask_query}
            ]

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=500
            )

            response_message = response.choices[0].message

            if response_message.tool_calls:
                messages.append(response_message)
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    if function_name == "rank_corridors":
                        tool_result = rank_corridors(
                            dataset=dataset,
                            metro_id=args.get("region"),
                            archetype_id=args.get("archetype_id"),
                            audience_segment_id=args.get("audience_segment_id"),
                            period=args.get("period"),
                            top_k=5
                        )
                    elif function_name == "get_corridor_summary":
                        tool_result = get_corridor_summary(
                            dataset=dataset,
                            corridor_id=args.get("corridor_id"),
                            archetype_id=args.get("archetype_id"),
                            audience_segment_id=args.get("audience_segment_id"),
                            period=args.get("period")
                        )
                    else:
                        tool_result = {"error": f"Unknown tool {function_name}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(tool_result)
                    })

                second_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500
                )
                final_answer = second_response.choices[0].message.content
            else:
                final_answer = response_message.content

            if final_answer:
                st.info(final_answer)

    except Exception as e:
        st.error(f"Error executing Ask CorridorIQ: {str(e)}")
