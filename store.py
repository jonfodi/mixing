"""Saves every session to disk. A restart loses nothing, and feedback.py can score every turn later.
SQLite is one file and ships with Python. Many artists on one system would need a server database like Postgres."""
import json
import os
import sqlite3
import subprocess

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

DB = os.environ.get("SOUND_DB", "sound.db")

SCHEMA = """
create table if not exists sessions (
    id integer primary key, started text default current_timestamp,
    version text, model text, variant text, history text
);
create table if not exists turns (
    session integer, n integer, message text, reply text, steps text,
    before text, after text, touched text, brief text, seconds real,
    primary key (session, n)
);
create table if not exists scores (
    session integer, n integer, sentiment real, reason text,
    primary key (session, n)
);
"""


def connect(path=DB):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def version():
    """The git commit, with -dirty when there are changes not committed yet. This links every score to the code."""
    out = subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True, text=True).stdout.strip()
    return out or "unknown"


def _plain(o):
    # Sets become lists. SDK blocks like thinking and tool_use become the dicts the API accepts back.
    return sorted(o) if isinstance(o, set) else o.to_dict()


def dump(o):
    return json.dumps(o, default=_plain)


def start(db, model, variant):
    cur = db.execute("insert into sessions (version, model, variant) values (?, ?, ?)", (version(), model, variant))
    db.commit()
    return cur.lastrowid


# A locked file often clears in a moment. A full disk does not, so after 3 tries the error goes up and the session stops.
@retry(retry=retry_if_exception_type(sqlite3.Error), stop=stop_after_attempt(3), wait=wait_fixed(0.5), reraise=True)
def save_turn(db, session, n, message, reply, steps, turn, after, brief, history, seconds):
    # One transaction. A failure undoes both writes, so a retry starts clean.
    with db:
        db.execute(
            "insert into turns values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session, n, message, reply, dump(steps), dump(turn["before"]), dump(after), dump(turn["touched"]), dump(brief), seconds),
        )
        # The whole conversation, so --resume can send it to the model again.
        db.execute("update sessions set history = ? where id = ?", (dump(history), session))


def load(db, session=None):
    """The last session, or the one named. Returns its id, history, brief, turns, and model in the shapes llm.py uses."""
    row = db.execute("select * from sessions where id = coalesce(?, (select max(id) from sessions))", (session,)).fetchone()
    rows = db.execute("select * from turns where session = ? order by n", (row["id"],)).fetchall()
    turns = [{"before": json.loads(r["before"]), "touched": set(json.loads(r["touched"]))} for r in rows]
    brief = json.loads(rows[-1]["brief"]) if rows else {"theme": "", "decisions": []}
    return row["id"], json.loads(row["history"] or "[]"), brief, turns, row["model"]
