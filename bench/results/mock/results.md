# Benchmark results (mock)

> **MOCK MODE.** These results come from the scripted oracle provider, which is given the reference solution and fails on purpose on some tasks. They only prove the harness works; they say nothing about the agent's real ability. Token counts are chars/4 estimates and costs are what those tokens would cost at `claude-opus-5-5` prices.

## Summary

| strategy | pass@1 | avg steps | total tokens | avg tokens | cost (USD) | avg wall (s) |
|---|---|---|---|---|---|---|
| direct | 15/20 (75%) | 7.3 | 167,604 | 8,380 | 0.73 | 0.69 |
| plan | 15/20 (75%) | 8.2 | 193,831 | 9,692 | 0.84 | 0.76 |

## Failure taxonomy

| category | direct | plan |
|---|---|---|
| provider_error | 0 | 0 |
| budget_exceeded | 1 | 1 |
| broken_patch | 1 | 1 |
| gave_up | 1 | 1 |
| wrong_file | 1 | 1 |
| test_overfit | 1 | 1 |
| incorrect_fix | 0 | 0 |

## Per task

| task | bug category | strategy | result | stop reason | steps | tokens |
|---|---|---|---|---|---|---|
| 01_pagination_off_by_one | off-by-one | direct | pass | finished | 6 | 5,858 |
| 02_moving_average_window | off-by-one | direct | pass | finished | 6 | 5,652 |
| 03_median_even_length | edge case | direct | pass | finished | 8 | 8,584 |
| 04_email_regex | bad regex | direct | fail: test_overfit | finished | 6 | 5,563 |
| 05_mutable_default_cart | mutable default argument | direct | pass | finished | 6 | 5,659 |
| 06_async_gather | async bug | direct | pass | finished | 6 | 5,728 |
| 07_async_lock_race | async bug | direct | fail: broken_patch | gave_up | 6 | 6,661 |
| 08_celsius_integer_division | wrong operator | direct | pass | finished | 6 | 5,242 |
| 09_truncate_ellipsis | edge case | direct | pass | finished | 6 | 5,493 |
| 10_dict_mutation_cache | mutation during iteration | direct | fail: wrong_file | finished | 6 | 6,095 |
| 11_binary_search_bounds | off-by-one | direct | pass | finished | 6 | 5,777 |
| 12_leap_year_century | edge case | direct | pass | finished | 6 | 5,337 |
| 13_roman_subtractive | incomplete logic | direct | fail: gave_up | gave_up | 4 | 3,327 |
| 14_csv_quoted_fields | parsing | direct | pass | finished | 8 | 8,466 |
| 15_late_binding_closure | closure late binding | direct | pass | finished | 6 | 5,318 |
| 16_money_split_rounding | floating point | direct | pass | finished | 6 | 5,550 |
| 17_date_range_inclusive | off-by-one | direct | fail: budget_exceeded | max_steps | 30 | 55,771 |
| 18_flatten_strings | edge case | direct | pass | finished | 6 | 6,167 |
| 19_grid_shared_rows | aliasing | direct | pass | finished | 6 | 5,491 |
| 20_sort_multi_key | wrong sort key | direct | pass | finished | 6 | 5,865 |
| 01_pagination_off_by_one | off-by-one | plan | pass | finished | 7 | 7,197 |
| 02_moving_average_window | off-by-one | plan | pass | finished | 7 | 6,994 |
| 03_median_even_length | edge case | plan | pass | finished | 9 | 10,112 |
| 04_email_regex | bad regex | plan | fail: test_overfit | finished | 7 | 6,910 |
| 05_mutable_default_cart | mutable default argument | plan | pass | finished | 7 | 7,003 |
| 06_async_gather | async bug | plan | pass | finished | 7 | 7,070 |
| 07_async_lock_race | async bug | plan | fail: broken_patch | gave_up | 7 | 7,993 |
| 08_celsius_integer_division | wrong operator | plan | pass | finished | 7 | 6,559 |
| 09_truncate_ellipsis | edge case | plan | pass | finished | 7 | 6,834 |
| 10_dict_mutation_cache | mutation during iteration | plan | fail: wrong_file | finished | 7 | 7,435 |
| 11_binary_search_bounds | off-by-one | plan | pass | finished | 7 | 7,125 |
| 12_leap_year_century | edge case | plan | pass | finished | 7 | 6,677 |
| 13_roman_subtractive | incomplete logic | plan | fail: gave_up | gave_up | 5 | 4,458 |
| 14_csv_quoted_fields | parsing | plan | pass | finished | 9 | 10,006 |
| 15_late_binding_closure | closure late binding | plan | pass | finished | 7 | 6,643 |
| 16_money_split_rounding | floating point | plan | pass | finished | 7 | 6,890 |
| 17_date_range_inclusive | off-by-one | plan | fail: budget_exceeded | max_steps | 30 | 56,379 |
| 18_flatten_strings | edge case | plan | pass | finished | 7 | 7,508 |
| 19_grid_shared_rows | aliasing | plan | pass | finished | 7 | 6,822 |
| 20_sort_multi_key | wrong sort key | plan | pass | finished | 7 | 7,216 |
