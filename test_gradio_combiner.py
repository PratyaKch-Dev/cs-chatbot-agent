"""
Test the two-phase combiner logic without running Gradio or the pipeline.

Phase 1 — enqueue_msg: push(message) → instant, clears input, appends user bubble
Phase 2 — process_messages: claim() → slow pipeline → final state

Verifies:
  1. Single message flows through correctly
  2. When Q2 arrives while Q1 is processing, gen1 is superseded and gen2 answers both
  3. Second round keeps previous history intact
"""

import threading
import sys
sys.path.insert(0, ".")

from pipeline.combiner import push, claim, is_current, complete, reset

TENANT = "test"
USER   = "u1"


def fake_pipeline(combined: str) -> str:
    import time
    time.sleep(0.3)
    return f"ANSWER({combined})"


def simulate_enqueue(message, chatbot_state):
    """Mirrors enqueue_msg: instant, returns new chatbot state."""
    push(TENANT, USER, message)
    return chatbot_state + [[message, ""]]


def simulate_process(chatbot_state):
    """Mirrors process_messages generator: claims batch, runs pipeline, returns states."""
    gen, messages = claim(TENANT, USER)
    if gen is None or not messages:
        return [("no_op", None)]

    states = []
    combined = "\n".join(messages)
    reply = fake_pipeline(combined)

    if not is_current(TENANT, USER, gen):
        states.append(("superseded", None))
        return states

    complete(TENANT, USER)
    base = [h for h in chatbot_state if h[1] not in ("", None)]
    final = base + [[msg, ""] for msg in messages[:-1]] + [[messages[-1], reply]]
    states.append(("final_yield", [list(h) for h in final]))
    return states


def run_process(chatbot_state, results, key, barrier):
    states = simulate_process(chatbot_state)
    barrier.wait()
    results[key] = states


def test_single_message():
    reset(TENANT, USER)
    chatbot = simulate_enqueue("Q1", [])
    assert chatbot == [["Q1", ""]], f"FAIL enqueue: {chatbot}"

    states = simulate_process(chatbot)
    assert states[0] == ("final_yield", [["Q1", "ANSWER(Q1)"]]), f"FAIL final: {states[0]}"
    print("PASS  single message")


def test_two_messages_fast():
    """Q2 arrives and claims while Q1's pipeline is running."""
    reset(TENANT, USER)
    results = {}
    barrier = threading.Barrier(3)  # proc1 + proc2 + main

    # Enqueue both messages (phase 1 is instant so order doesn't matter much)
    simulate_enqueue("Q1", [])
    # proc1 claims Q1 and starts running
    # proc2 will push Q2 and claim (getting inflight Q1 + pending Q2)

    def proc1():
        # claim Q1 first (Q1 already in pending from enqueue above)
        states = simulate_process([["Q1", ""]])
        barrier.wait()
        results["proc1"] = states

    def proc2():
        import time
        time.sleep(0.05)  # ensure proc1 has claimed Q1 first
        simulate_enqueue("Q2", [["Q1", ""]])
        states = simulate_process([["Q1", ""], ["Q2", ""]])
        barrier.wait()
        results["proc2"] = states

    t1 = threading.Thread(target=proc1)
    t2 = threading.Thread(target=proc2)
    t1.start(); t2.start()
    barrier.wait()
    t1.join(); t2.join()

    p1, p2 = results["proc1"], results["proc2"]

    # proc1 must be superseded (Q2 arrived mid-flight)
    assert any(s[0] == "superseded" for s in p1), f"proc1 should be superseded: {p1}"

    # proc2 must produce the combined answer
    final = next(s for s in p2 if s[0] == "final_yield")
    assert final[1] == [["Q1", ""], ["Q2", "ANSWER(Q1\nQ2)"]], f"FAIL final: {final}"

    print("PASS  two messages fast (proc2 combines Q1+Q2)")


def test_second_round_keeps_history():
    """After first batch completes, the second message sees completed history."""
    reset(TENANT, USER)

    # First message
    chatbot = simulate_enqueue("Q1", [])
    states = simulate_process(chatbot)
    final_state = next(s[1] for s in states if s[0] == "final_yield")
    assert final_state == [["Q1", "ANSWER(Q1)"]], f"unexpected first round: {final_state}"

    # Second message — history has completed Q1
    chatbot2 = simulate_enqueue("Q2", final_state)
    states2 = simulate_process(chatbot2)
    final2 = next(s[1] for s in states2 if s[0] == "final_yield")

    assert final2[0] == ["Q1", "ANSWER(Q1)"],   f"Q1 dropped: {final2}"
    assert final2[1] == ["Q2", "ANSWER(Q2)"],   f"Q2 wrong: {final2}"

    print("PASS  second round keeps full history")


if __name__ == "__main__":
    test_single_message()
    test_two_messages_fast()
    test_second_round_keeps_history()
    print("\nAll tests passed.")
