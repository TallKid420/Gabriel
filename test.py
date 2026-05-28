from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core._api.beta_decorator import LangChainBetaWarning
from pathlib import Path

import warnings
import sqlite3

# Hide v3 experimental warnings caused by version="v3"
warnings.filterwarnings(
    "ignore",
    category=LangChainBetaWarning
)

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's always sunny in {city}!"

llm = ChatOllama(
    model="gpt-oss:20b",
    base_url="http://jcs-macbook-pro:11434",
)

DB_PATH = Path("data/checkpoints/checkpoints.sqlite")

# create parent folders automatically
DB_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

memory = SqliteSaver(conn)

agent = create_agent(
    model=llm,
    tools=[get_weather],
    checkpointer=memory
)

config = {
    "configurable": {
        "thread_id": "user-session-1"
    }
}

stream = agent.stream_events({
    "messages": [{"role": "user", "content": "What is the weather in SF?"}],
}, config=config, version="v3")


for message in stream.messages:
    for delta in message.text:
        print(delta, end="", flush=True)

final_state = stream.output