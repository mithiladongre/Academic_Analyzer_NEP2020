import os
import ast
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
import chromadb

load_dotenv()

print("Loading Database and AI Embeddings into RAM...")
CHROMA_CLIENT = chromadb.PersistentClient(path="./chroma_db")
CHROMA_COLLECTION = CHROMA_CLIENT.get_or_create_collection(name="academic_insights")
EMBEDDINGS = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def ask_rag_agent(question: str, file_id: str) -> str:
    # 1. INSTANT LOCAL RETRIEVAL
    query_embedding = EMBEDDINGS.embed_query(question)
    results = CHROMA_COLLECTION.query(
        query_embeddings=[query_embedding],
        n_results=5, 
        where={"file_id": file_id}
    )
    
    context_data = "No specific data found for this query."
    if results['documents'] and results['documents'][0]:
        context_data = "\n".join(results['documents'][0])

    llm = ChatGoogleGenerativeAI(
        model="models/gemini-3.1-flash-lite-preview", 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        max_retries=1 
    )
    
    system_prompt = f"""
    You are the Academic Advisor for PICT. You are analyzing the result file: {file_id}.
    
    Answer the user's question based ONLY on this retrieved database context:
    <database_data>
    {context_data}
    </database_data>
    
    User Question: {question}
    
    CRITICAL DATA RULES:
    1. Do NOT invent grades or guess missing values.
    2. NEVER calculate the SGPA, Totals, or Credits yourself.
    3. If a specific metric like SGPA is NOT explicitly written in the data, output 'N/A (Backlog)' or 'Not Provided'.
    
    CRITICAL FORMATTING RULES:
    1. Never output a raw block of text.
    2. Use Markdown headings (###) to separate sections.
    3. Present grades and marks using bullet points or Markdown tables.
    4. Bold key metrics like SGPA, total marks, and final grades.
    5. Provide a short 'Insights & Recommendations' section at the end.
    """
    
    response = llm.invoke(system_prompt)
    raw_content = response.content
    
    # 3. EXTRACTION
    if isinstance(raw_content, str) and raw_content.strip().startswith("[{"):
        try:
            parsed_list = ast.literal_eval(raw_content)
            clean_text = ""
            for item in parsed_list:
                if isinstance(item, dict) and "text" in item:
                    clean_text += item["text"]
            return clean_text
        except Exception:
            pass 

    if isinstance(raw_content, list):
        clean_text = ""
        for item in raw_content:
            if isinstance(item, dict) and "text" in item:
                clean_text += item.get("text", "")
            elif isinstance(item, str):
                clean_text += item
        return clean_text
        
    return raw_content