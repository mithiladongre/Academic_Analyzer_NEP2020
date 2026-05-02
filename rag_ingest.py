import os
import pandas as pd
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
import chromadb
import json

load_dotenv()

def get_chroma_collection():
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="academic_insights")
    return collection

def ingest_data_to_vector_db(file_id, df):
    collection = get_chroma_collection()
    
    print("Loading local embedding model (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    documents = []
    metadatas = []
    ids = []
    
    for index, row in df.iterrows():
        row_dict = {str(k): str(v) for k, v in row.items() if pd.notna(v) and v != ""}
        seat = row_dict.get("SEAT NO", "Unknown")
        name = row_dict.get("Name", "Unknown")
        
        chunk_text = (
            f"Record for {name} ({seat}). "
            f"Data: {json.dumps(row_dict)}"
        )
        
        documents.append(chunk_text)
        metadatas.append({"file_id": file_id, "type": "full_record", "seat": seat})
        ids.append(f"{file_id}_{seat}")

    print(f"Starting lightning ingestion of {len(documents)} records...")
    
    try:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings.embed_documents(documents)
        )
        print(f"✅ Successfully indexed all {len(documents)} records instantly!")
    except Exception as e:
        print(f"⚠️ Error during ingestion: {e}")
    
    print(f"🏁 Finished ingestion for {file_id}")
    return True