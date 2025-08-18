import os
import time


def main(iters: int = 400):
    # Lazily import so env vars are loaded before settings
    from app.main import reinit_executor_for_tests, executor

    # Reinitialize to pick up current env settings (VIDEO_*)
    reinit_executor_for_tests()

    worked = 0
    for _ in range(iters):
        if executor.run_once():
            worked += 1
        else:
            time.sleep(0.02)
    print(f"worker iterations={iters} tasks_processed={worked}")


if __name__ == "__main__":
    n = int(os.getenv("RUN_ITERS", "400"))
    main(n)
