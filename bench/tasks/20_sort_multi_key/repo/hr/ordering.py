def sort_employees(employees):
    """`employees` is a list of dicts with "name", "dept" and "salary"."""
    return sorted(employees, key=lambda e: (e["dept"], e["salary"]), reverse=True)
