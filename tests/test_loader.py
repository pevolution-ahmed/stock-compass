from compass.modules.loader import STEPS, progress


def test_progress_counts_errors_as_finished():
    keys = [key for key, _ in STEPS]
    states = dict.fromkeys(keys, "running")
    assert progress(states)["fraction"] == 0 and not progress(states)["done"]

    states[keys[0]] = "done"
    states[keys[1]] = "error"  # a failed source must not keep the loader up forever
    assert progress(states)["fraction"] == 2 / len(keys)

    finished = progress(dict.fromkeys(keys, "done"))
    assert finished["done"] and finished["fraction"] == 1
    assert [s["key"] for s in finished["steps"]] == keys
