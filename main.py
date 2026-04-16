from hf import generate_response
import requests
import io
import config
import re
import streamlit as st
from io import BytesIO
from huggingface_hub import InferenceClient 


MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
FILTER_API_URL = "https://filters-zeta.vercel.app/api/filter"
ENHANCE_SYS = (
"Improve prompts for text-to-image. Return ONLY the enhanced prompt. "
"Add subject, style, lighting, camera angle, background, colors. Keep it safe."
)
NEGATIVE = "low quality, blurry, distorted, watermark, text, cropped"

img_client = InferenceClient(provider="hf-inference", api_key=config.HF_API_KEY)

MATH_SYSTEM = """You are a Math Mastermind. For every math problem:

1) Show step-by-step solution 2) Explain reasoning 3) Give alternate method if possible

4) Verify answer if possible 5) Use proper notation 6) Break complex problems into parts

Format: Problem → Steps → **Final Answer** → Concepts used. Be precise and educational."""

CHAT_CSS = """

<style>

.wrap {max-height: 520px; overflow-y: auto; padding-right: 6px;}

.card{border:1px solid #e6e6e6;background:#fff;border-radius:10px;padding:14px 16px;margin:10px 0;

box-shadow:0 1px 2px rgba(0,0,0,0.04);}

.q{font-weight:700;color:#0a6ebd;margin-bottom:8px;}

.meta{display:inline-block;background:#FF9800;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;margin-left:8px}

.a{white-space:pre-wrap;color:#333;line-height:1.5;}

</style>

"""
def  math_generate(problem: str, level: str, temperature=0.1, max_tokens=1024) -> str:
    prompt = f"{MATH_SYSTEM}\n\nMath Problem ({level}: {problem})"
    return generate_response(prompt, temperature=temperature,max_tokens=max_tokens)

def export_txt(history):
  txt = "\n\n".join([f"Q{i}: {h['question']}\nA{i}: {h['answer']}" for i, h in enumerate(history, 1)])
  return io.BytesIO(txt.encode("utf-8"))
def check_prompt_with_filter_api(prompt: str):
    try:
        response = requests.post(
            FILTER_API_URL,
            json={"prompt": prompt},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            return {"ok": False, "reason": "Invaild filter API response."}
        return data
    except Exception as e:
        return{
            "ok": False,
            "reason": f"Filter API Error: {str(e)}",
        }
def enhance_prompt(raw: str) -> str:
    from hf import generate_response

    out = generate_response(
        f"{ENHANCE_SYS}\nUser prompt: {raw}",
        temperature=0.4,
        max_tokens=220,
    )    
    return (out or raw).strip()

def gen_image(prompt: str):
    filter_result = check_prompt_with_filter_api(prompt)
    if not filter_result.get("ok"):
        return None, f"⚠️ Prompt blocked by safety filter. {filter_result.get('reason', 'Unsafe prompt')}"
    try: 
        return img_client.text_to_image(prompt=prompt,negative_prompt=NEGATIVE,model=MODEL_ID,),None
    except Exception as e:
        msg = str(e)
        if "negative_prompt" in msg or "unexpected keyword" in msg:
            try:
                return img_client.text_to_image(
                    prompt=prompt,
                    model=MODEL_ID,
                ), None
            except Exception as e2:
                msg = str(e2)

        if any(x in msg for x in ["402", "Payment Required", "pre-paid credits"]):
            return None, "❌ Image backend requires credits or model not available on hf-inference.\n\nRaw error: " + msg

        if "404" in msg or "Not Found" in msg:
            return None, "❌ Model not served on this provider route (hf-inference).\n\nRaw error: " + msg

        return None, "Error during image generation: " + msg

def teaching_answer(q: str) -> str:
  return generate_response(q, temperature=0.3, max_tokens=1024)

def math_answer(q: str, level:str) -> str:
  prompt = f"{MATH_SYSTEM}\n\nDifficulty: {level}\nMath Problem: {q}"
  return generate_response(prompt, temperature=0.1, max_tokens=1024)

def run_ai_teaching_assistant():
  st.set_page_config(page_title="AI Teaching Assistant", layout="centered")
  st.title("🤖 AI Teaching Assistant")
  st.write("Ask me anything about various subjects, and I'll provide an insightful answer. ")
  st.session_state.setdefault("history", [])

  col_clear, col_export = st.columns([1, 2])
  with col_clear:
    if st.button("🧹 Clear Conversation"):
      st.session_state.history = []
      st.rerun()
  with col_export:
    if st.session_state.history:
      st.download_button(
        label="◀️ Export Chat History",
        data=export_txt(st.session_state.history),
        file_name="AI_Teaching_Assistant_Converstaion.txt",
        mime ="text/plain",
      )
  user_input = st.text_input("Enter your question here:")
  if st.button("Ask"):
    q = user_input.strip()
    if q:
      with st.spinner("Generating AI Response..."):
        a = generate_response(q, temperature=0.3)
      st.session_state.history.insert(0, {"question": q, "answer": a})
      st.rerun()
    else:
      st.warning("⚠️ Please enter a question before clicking Ask.")
  st.markdown('### Conversation History')
  st.markdown(CHAT_CSS,unsafe_allow_html=True)

  cards = []
  for i, h in enumerate(st.session_state.history, 1):
    cards.append(f'<div class="qa-card"><div class="q">Q{i}: {h["question"]}</div><div class="a">{h["answer"]}</div></div>')
  st.markdown('<div class="history-wrap">' + "".join(cards) + "</div>", unsafe_allow_html=True)

def run_math_mastermind():
   st.set_page_config(page_title="🧮 Math Mastermind", layout="centered")
   st.title("🧮 Math Mastermind")
   st.write("Solve any math problem with detailed step-by-step explanations. ")

   with st.expander("📌 Examples"):
    st.markdown(
    '- Algebra: "Solve 2x² + 5x − 3 = 0"\n'
    '- Calculus: "Derivative of sin(x²) + ln(x)"\n'
    '- Geometry: "Area of triangle (0,0),(3,4),(6,0)"\n'
    '- Probability: "P(sum=7 with two dice)"'
    )
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("k", 0)
    c1, c2 = st.columns([1, 2])
    if c1.button("🗑️ Clear"):
        st.session_state.history = []; st.rerun()

    if st.session_state.history:
        c2.download_button("📄 Export", export_txt(st.session_state.history),
                           "Math_Mastermind_Solutions.txt", "text/plain")

    with st.form("math_form", clear_on_submit=True):
        q = st.text_area("📝 Enter your math problem:", height=100,
                         placeholder="Example: Solve x² + 5x + 6 = 0",
                         key=f"q_{st.session_state.k}")
        a, b = st.columns([3, 1])
        solve = a.form_submit_button("🧠 Solve", use_container_width=True)
        level = b.selectbox("Level", ["Basic", "Intermediate", "Advanced"], index=1)

        if solve:
           if not q.strip(): st.warning("⚠️ Enter a problem first.")
           else:
              with st.spinner("Solving..."):
                 ans = math_generate(q.strip(), level)
              st.session_state.history.insert(0, {"question": q.strip(), "answer": ans,"lvl": level})
              st.session_state.k += 1; st.rerun()

    if not st.session_state.history: return
    st.markdown("### 🧾 Solution History (Latest First)")
    st.markdown("""<style>
    .box{max-height:500px;overflow-y:auto;border:2px solid #4CAF50;padding:12px;background:#f7fbff;border-radius:10px}
    .q{font-weight:700;color:#2E7D32;margin-top:12px}
    .lvl{display:inline-block;background:#FF9800;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;margin-left:8px}
    .a{white-space:pre-wrap;color:#1B5E20;background:#fff;padding:10px;border-radius:8px;border-left:4px solid #4CAF50;margin:6px 0 14px}
    </style>""", unsafe_allow_html=True)

    html = '<div class= "box">'
    for i,h in enumerate(st.session_state.history, 1):
       html += f'<div class="q">Q{i}: {h["question"]}<span class="lvl>{h["lvl"]}<span></div>'
       html += f'<div class="a">{h["answer"]}</div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)

def run_safe_ai_image_generator():
    st.set_page_config(page_title="Safe AI Image Generator",   layout="centered")
    st.title("🖼️ Safe AI Image Generator")
    st.info("Flow: Enter a prompt → enhance it → check it using the deployed safety API → generate the image.")

    with st.form("image_form"):
        raw = st.text_area(
            "Image Description",
            height=120,
            placeholder="Example: A cozy cabin in snowy mountains at sunrise, cinematic lighting",
        )
        submit = st.form_submit_button("Generate Image")

    if submit:
        raw = raw.strip()

        if not raw:
            st.warning("⚠️ Please enter an image description.")
            return

        raw_check = check_prompt_with_filter_api(raw)
        if not raw_check.get("ok"):
            st.error(f"⚠️ Prompt blocked. {raw_check.get('reason', 'Unsafe prompt')}")
            return

        with st.spinner("Enhancing your prompt..."):
            final_prompt = enhance_prompt(raw)

        enhanced_check = check_prompt_with_filter_api(final_prompt)
        if not enhanced_check.get("ok"):
            st.error(f"⚠️ Enhanced prompt blocked. {enhanced_check.get('reason', 'Unsafe prompt')}")
            return

        st.markdown("#### Enhanced Prompt")
        st.code(final_prompt)

        with st.spinner("Generating image..."):
            img, err = gen_image(final_prompt)

        if err:
            st.error(err)
            return

        st.image(img, caption="Generated Image", use_container_width=True)
        st.session_state.generated_image = img

    img = st.session_state.get("generated_image")
    if img:
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.download_button(
            "📥 Download Image",
            buf.getvalue(),
            "ai_generated_image.png",
            "image/png",
        )
   

def main():
   st.sidebar.title("Choose AI Feature")
   opt = st.sidebar.selectbox("", ["AI Teaching Asistant", "Math Mastermind", "Safe AI Image Generator"])
   if opt == "AI Teaching Asistant": run_ai_teaching_assistant()
   elif opt == "Math Mastermind": run_math_mastermind()
   else:  run_safe_ai_image_generator()

if __name__=="__main__":
   main()   
   