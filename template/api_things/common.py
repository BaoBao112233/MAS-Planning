def cron_to_custom_format(cron_expr: str):
    parts = cron_expr.strip().split()
    if len(parts) != 6:
        raise ValueError("Cron expression must have 6 fields (second, minute, hour, day, month, weekday)")

    _, minute, hour, day, month, weekday = parts

    # Trường hợp 1: Lịch chạy 1 lần (có số cụ thể cho day và month, và weekday là '?' hoặc '*')
    if day.isdigit() and month.isdigit() and weekday in ['?', '*']:
        j = [int(day), int(month), int(hour), int(minute)]
        w = []

    # Trường hợp 2: Lịch chạy theo thứ (weekday có số, day là '?')
    elif weekday not in ['?', '*']:
        j = [0, 0, 0 if hour == '*' else int(hour), 0 if minute == '*' else int(minute)]
        if ',' in weekday:
            w = [int(wd) for wd in weekday.split(',')]
        elif '-' in weekday:
            start, end = map(int, weekday.split('-'))
            w = list(range(start, end + 1))
        else:
            w = [int(weekday)]

    # Trường hợp 3: Lặp lại không theo thứ cụ thể (cả day và weekday là '*')
    elif weekday in ['*', '?'] and day in ['*', '?']:
        j = [0, 0, 0 if hour == '*' else int(hour), 0 if minute == '*' else int(minute)]
        w = [0,1,2,3,4,5,6]

    # Trường hợp khác (ví dụ day = '*', weekday = '?') => cũng là lịch lặp
    else:
        j = [0, 0, 0 if hour == '*' else int(hour), 0 if minute == '*' else int(minute)]
        w = [0,1,2,3,4,5,6]

    return {
        "j": j,
        "w": w
    }