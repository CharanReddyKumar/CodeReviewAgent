import streamlit as st
import sqlite3
import json
import pickle
from typing import Any

st.set_page_config(page_title="Code Review Agent - Gatekeeper", layout="wide")

st.title("Code Review Agent - Human Gatekeeper")

# Connect to checkpoint DB
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
cursor = conn.cursor()

# Fetch active threads
cursor.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id DESC")
threads = [row[0] for row in cursor.fetchall()]

selected_thread = st.sidebar.selectbox("Select Review Session", threads)

if selected_thread:
    st.sidebar.write(f"Session ID: {selected_thread}")
    
    # Fetch latest state
    cursor.execute(
        "SELECT checkpoint FROM checkpoints WHERE thread_id = ? ORDER BY thread_ts DESC LIMIT 1", 
        (selected_thread,)
    )
    row = cursor.fetchone()
    
    if row:
        # Checkpoints are stored as pickled blobs in LangGraph SqliteSaver
        # Note: This depends on the exact serialization format of SqliteSaver
        # For this demo, we assume we can unpickle it or it's JSON.
        # In reality, LangGraph uses a specific serializer.
        try:
            checkpoint_data = pickle.loads(row[0])
            state = checkpoint_data.get("channel_values", {})
            
            st.header("Current State")
            st.json(state)
            
            if st.button("Approve & Publish"):
                st.success("Review approved! (Mock action)")
                # In a real app, we would update the state to resume the graph
                
            if st.button("Reject & Refine"):
                st.warning("Sent back for refinement! (Mock action)")
                
        except Exception as e:
            st.error(f"Failed to load checkpoint: {e}")
    else:
        st.info("No checkpoints found for this session.")
else:
    st.info("Select a session to view.")
