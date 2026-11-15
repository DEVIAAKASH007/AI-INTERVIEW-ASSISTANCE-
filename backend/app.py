from flask import Flask,request
from dotenv import load_dotenv
import os
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
import json
import requests
import base64
from flask_cors import CORS,jsonify,json
import tempfile
import assemblyai as aai


load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MURF_API_KEY=os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY=os.getenv("ASSEMBLYAI_API_KEY")

model = init_chat_model(
    "google_genai:gemini-3.5-flash-lite",
    api_key=GEMINI_API_KEY
)
def stream_audio(text):
    
    url = "https://global.api.murf.ai/v1/speech/stream"
    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }
    data = {  
    "voice_id": {"voice_id":"Namrita","style":"Conversational"},
    "text": text,
    "locale": "hi-IN",
    "model": "FALCON",
    "format": "MP3",
    "sampleRate": 24000,
    "channelType": "MONO"
    }

    response = requests.post(url, headers=headers, json=data, stream=True)

    if response.status_code == 200:
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                yield base64.b64encode(chunk).decode("utf-8")+"\n"
                
    else:
        print(f"Error: {response.status_code}")



create_agent(
    model=model,
    tools=[],
    checkpointer=InMemorySaver()
    
)
current_subject = ""
question_count = 0
thread_id="interview_session-1"
interview_prompt="""you are a ai interviewer, you will ask questions to the user based on the subject provided{}.
You will ask 5 questions in total, and after each question, you will wait for the user's answer before asking the next question. 
After the user answers all 5 questions, you will provide a summary of the user's performance and give feedback on their answers. 
The questions should be relevant to the subject provided and should be designed to assess the user's knowledge and understanding of the subject."""


app = Flask(__name__)
CORS(app,expose_headers=["X-Question-number"])

@app.route("/start-interview", methods=["POST"])

def start_interview():
    global current_subject,question_count,checkpoint,agent
    data = request.json
    current_subject = data.get("subject","python")
    question_count=1
    
    
    checkpoint = InMemorySaver()
    
    agent=create_agent(
        model=model,
        tools=[],
        checkpointer=checkpoint
    )
    formatted_prompt = interview_prompt.format(current_subject)
    config={"configurable":{
        "thread_id":thread_id,
    }}
    
    responce= agent.invoke({
        "messages":[{"role":"system","content":formatted_prompt},
                    {"role":"user","content":"start the interview with a warm welcome and ask the first question {current_subject} keep it short 1-2 sentences."}],

                    
    },config=config)
    
    
    question = responce["messages"][-1].content
    return stream_audio(question),{"content-type":"text/plain"}

def speech_to_text(audio_path):
    transcriber = aai.Transcriber()
    transcribe=transcriber.transcribe(audio_path)
    return transcribe.text if transcribe.text else ""
    


@app.route("/submit-answer", methods=["POST"])
def submit_answer():
    global question_count
    audio_file=request.files['audio']
    question_count+=1
    temp_file=(tempfile.NamedTemporaryFile(
        delete=False ,
        suffix=".webm")).name
    audio_file.save(temp_file)
    answer=speech_to_text(temp_file)
    os.unlink(temp_file)
    if not answer:
        answer="there is no answer provided by the user"
   
    config={"configurable":{
        "thread_id":thread_id,
    }}
    responce= agent.invokke({
        "messages":[{"role":"user","content":answer}]
    },config=config)
    
    prompt=f"the candidate answered the question as follows: {answer}. please provide feedback on the answer and ask the next question. keep it short 1-2 sentences. if they said wrong answer or i dont know then ask next question simply without providing feedback. if this is the last question then provide a summary of the candidate's performance and give feedback on their answers."
    responce= agent.invoke({
        "messages":[{"role":"user","content":prompt}]
    },config=config)
    question = responce["messages"][-1].content
    return stream_audio(question),{"content-type":"text/plain" ,
                                   "X-Question-number":str(question_count)}
    
    
    
feedback_prompt="""you are a ai interviewer, you will provide feedback on the user's answers based on the subject provided .
You will provide a summary of the user's performance and give feedback on their answers.
The feedback should be relevant to the subject provided and should be designed to assess the user's knowledge and understanding of the subject.
"""
    
@app.route("/get-feedback", methods=["POST"])
def get_feedback():
    config={"configurable":{
        "thread_id":thread_id,
    }}
    responce= agent.invoke({
        "messages":[{"role":"user","content": f"{feedback_prompt} \n review the entire interview on {current_subject}  and provide feedback on the user's answers."}]
    },config=config)
    text = responce["messages"][-1].content
    cleaned=text.strip()
    if "'''" in cleaned:
        cleaned=cleaned.replace("'''","")
    if cleaned.startswith("json"):
        cleaned=cleaned[len("json"):].strip()
    feedback=json.loads(cleaned)
    return jsonify({"success":True,"feedback":feedback})
    
    
    
    


app.run(debug=True, port=5000)
