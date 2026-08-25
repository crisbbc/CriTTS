import tkinter as tk
import timeit
import gc

def run_benchmark():
    num_children = 100
    num_iterations = 20000

    root = tk.Tk()
    frame1 = tk.Frame(root)
    frame2 = tk.Frame(root)
    for _ in range(num_children):
        tk.Label(frame1, text="test").pack()
        tk.Label(frame2, text="test").pack()
    root.update_idletasks()

    def bench_with_list():
        # Only measure the overhead of the list allocation
        children = list(frame1.winfo_children())
        for c in children:
            pass

    def bench_without_list():
        # Only measure without the list allocation
        children = frame2.winfo_children()
        for c in children:
            pass

    # Disable garbage collector for more stable timing
    gc.disable()
    try:
        # Warmup
        for _ in range(100):
            bench_with_list()
            bench_without_list()

        time_with_list = timeit.timeit(bench_with_list, number=num_iterations)
        time_without_list = timeit.timeit(bench_without_list, number=num_iterations)
    finally:
        gc.enable()

    print(f"Micro-benchmark results for iterating {num_children} children ({num_iterations} iterations):")
    print(f"With list():    {time_with_list:.5f} seconds")
    print(f"Without list(): {time_without_list:.5f} seconds")

    improvement = ((time_with_list - time_without_list) / time_with_list) * 100
    print(f"Improvement:    {improvement:.2f}%")

    root.destroy()

if __name__ == "__main__":
    run_benchmark()
