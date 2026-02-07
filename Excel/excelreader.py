# ...existing code...
import os
import sys
import pandas as pd
import datetime
import matplotlib.pyplot as plt

def read_sales_from_folder(folder, filename, period_label):
    csv_path = os.path.join(os.path.expanduser(folder), filename)
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return None
    # try common encodings
    df = None
    last_exc = None
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            df = pd.read_csv(csv_path, encoding=enc)
            break
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            last_exc = e
    if df is None:
        print(f"Failed to read CSV '{csv_path}': {last_exc}")
        return None
    df['Period'] = period_label
    return df

folder_m = '/Users/arnoldoramirezjr/Desktop/By Shift/Kingsville Morning'
folder_n = '/Users/arnoldoramirezjr/Desktop/By Shift/Kingsville Night'
filename = 'Sales by Day.csv'

# Show all rows/columns in console (be careful with very large files)
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

df_m = read_sales_from_folder(folder_m, filename, 'M')
df_n = read_sales_from_folder(folder_n, filename, 'N')

dfs = [d for d in (df_m, df_n) if d is not None]
if not dfs:
    print("No files were read from either folder.")
    sys.exit(1)

combined = pd.concat(dfs, ignore_index=True)

# --- New: detect date column, parse to datetime, and sort by date then Period (M before N) ---
candidates = ['yyyyMMdd', 'YYYYMMDD', 'Date', 'date', 'DAY', 'Day', 'day']
date_col = next((c for c in combined.columns if c in candidates), None)

if date_col is None:
    for c in combined.columns:
        lc = c.lower()
        if 'date' in lc or 'day' in lc or 'yyyy' in lc:
            date_col = c
            break

if date_col is not None:
    # Try parsing as strict YYYYMMDD first (remove trailing .0 often produced by Excel), then fallback to generic parsing
    cleaned = combined[date_col].astype(str).replace({r'\.0$': ''}, regex=True)
    parsed = pd.to_datetime(cleaned, format='%Y%m%d', errors='coerce')
    if parsed.isna().all():
        parsed = pd.to_datetime(cleaned, errors='coerce', dayfirst=False)
    combined['_sort_date'] = parsed
    # create a canonical Date column for plotting and further use
    combined['Date'] = parsed
else:
    combined['_sort_date'] = pd.NaT
    if 'Date' not in combined.columns:
        combined['Date'] = pd.NaT
    print("Warning: no date column detected; rows will not be date-sorted.")

# Use a numeric period order to avoid categorical sorting surprises: M -> 0, N -> 1, others -> 2
combined['Period'] = combined['Period'].astype(str)
combined['_period_order'] = combined['Period'].map({'M': 0, 'N': 1}).fillna(2).astype(int)

# Sort by date (ascending) then period order (M before N); keep stable ordering otherwise
combined = combined.sort_values(by=['_sort_date', '_period_order'], ignore_index=True, kind='stable')

# remove helper columns we no longer need
combined = combined.drop(columns=['_sort_date', '_period_order'])

# Print combined data
print(combined)

# Save combined file (optional) — ensure output directory exists
output_dir = os.path.expanduser('/Users/arnoldoramirezjr/Documents/AIO Python/Excel')
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'Sales_by_Day_combined.csv')
combined.to_csv(output_file, index=False)
print(f"Combined file saved to {output_file}")

# --- New section: create bar graph by date with separate bars for Period M and N ---
if combined.get('Date') is None or combined['Date'].isna().all():
    # try to infer Date from any likely column
    for c in combined.columns:
        lc = c.lower()
        if 'date' in lc or 'day' in lc or 'yyyy' in lc:
            cleaned = combined[c].astype(str).replace({r'\.0$': ''}, regex=True)
            dt = pd.to_datetime(cleaned, format='%Y%m%d', errors='coerce')
            if dt.isna().all():
                dt = pd.to_datetime(cleaned, errors='coerce')
            combined['Date'] = dt
            break

if combined['Date'].isna().all():
    print("No usable date column found for plotting. Skipping plot.")
else:
    plot_df = combined.dropna(subset=['Date']).copy()
    # normalize to datetime (no time) for grouping
    plot_df['Date'] = pd.to_datetime(plot_df['Date']).dt.date

    # detect a net sales column (case-insensitive)
    net_candidates = ['Net Sales', 'NetSales', 'Net_Sales', 'Net Amount', 'NetAmount', 'Net', 'Sales', 'Total']
    lower_map = {c.lower(): c for c in plot_df.columns}
    net_col = None
    for cand in net_candidates:
        if cand.lower() in lower_map:
            net_col = lower_map[cand.lower()]
            break

    # fallback: choose a numeric column that isn't QtyShip or Units
    if net_col is None:
        numeric_cols = plot_df.select_dtypes(include='number').columns.tolist()
        fallback_cols = [c for c in numeric_cols if c.lower() not in ('qtyship', 'qty', 'item qty', 'units')]
        net_col = fallback_cols[0] if fallback_cols else (numeric_cols[0] if numeric_cols else None)

    if net_col is None:
        print("No numeric column found to use as Net Sales. Skipping plot.")
    else:
        # coerce to numeric to avoid grouping errors
        plot_df[net_col] = pd.to_numeric(plot_df[net_col], errors='coerce').fillna(0)

        print(f"Using '{net_col}' as Net Sales for plotting.")
        # group by date and period, summing the net sales value
        pivot = plot_df.groupby(['Date', 'Period'])[net_col].sum().unstack(fill_value=0)

        # Ensure both M and N columns exist and order them M, N (others kept after)
        for col in ['M', 'N']:
            if col not in pivot.columns:
                pivot[col] = 0
        # keep columns in stable order: M, N, then others
        cols_order = [c for c in ['M', 'N'] if c in pivot.columns] + [c for c in pivot.columns if c not in ('M', 'N')]
        pivot = pivot[cols_order]
        pivot = pivot.sort_index()

        # Plot side-by-side bars for M and N (Net Sales)
        ax = pivot.plot(kind='bar', figsize=(12, 6), width=0.8)
        ax.set_xlabel('')
        ax.set_ylabel(f'Net Sales')
        ax.set_title(f'Net Sales by shift')
        plt.xticks(rotation=45, ha='right')
        plt.legend(title='Shift')
        plt.tight_layout()

        # Save plot (ensure output directory exists)
        plot_path = os.path.join(output_dir, 'Sales_by_Day_MN_net_sales_bar.png')
        try:
            plt.savefig(plot_path)
            print(f"Bar chart saved to {plot_path}")
        except Exception as e:
            print(f"Failed to save plot: {e}")
        # show plot if possible; in headless environments this may fail, so guard it
        try:
            plt.show()
        except Exception:
            # if display not available, just close the figure
            plt.close()
# Add dollar amount labels above each bar and re-save the figure (overwrites previous file)
# Guard all uses of ax/pivot/plot_path so this section is safe if plotting was skipped.
if 'ax' in locals() and ax is not None:
    try:
        # small offset above bars (1% of max height or a tiny fixed amount)
        y_max = pivot.values.max() if 'pivot' in locals() and pivot is not None else None
        offset = (abs(y_max) * 0.01) if y_max and y_max != 0 else 0.01

        for p in getattr(ax, "patches", []):
            h = p.get_height()
            if pd.isna(h):
                continue
            ax.annotate(
                '${:,.2f}'.format(h),
                xy=(p.get_x() + p.get_width() / 2, h + offset),
                ha='center',
                va='bottom',
                fontsize=8,
                rotation=0
            )

        # try to save the annotated figure (overwrite) if we have a path
        if 'plot_path' in locals() and plot_path:
            try:
                plt.savefig(plot_path)
                print(f"Bar chart with dollar labels saved to {plot_path}")
            except Exception as e:
                print(f"Failed to save labeled plot: {e}")
    except Exception as e:
        print(f"Failed to add dollar labels: {e}")
else:
    # No axes created (no plot) — skip labeling
    ax = None

# Add dollar amount labels using matplotlib.bar_label (works with grouped bars) if available
if 'ax' in locals() and ax is not None:
    try:
        fmt = '${:,.2f}'
        for container in getattr(ax, "containers", []):
            heights = [rect.get_height() for rect in container]
            labels = [fmt.format(h) if (h is not None and h != 0) else '' for h in heights]
            try:
                ax.bar_label(container, labels=labels, padding=3, fontsize=8, rotation=0)
            except Exception:
                # fallback: annotate manually if bar_label not available
                for rect, lbl in zip(container, labels):
                    if lbl:
                        ax.annotate(
                            lbl,
                            xy=(rect.get_x() + rect.get_width() / 2, rect.get_height()),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center',
                            va='bottom',
                            fontsize=8
                        )

        if 'plot_path' in locals() and plot_path:
            try:
                plt.savefig(plot_path)
                print(f"Bar chart with dollar labels saved to {plot_path}")
            except Exception as e:
                print(f"Failed to save labeled plot: {e}")
    except Exception as e:
        print(f"Failed to add dollar labels: {e}")

# show plot if possible; in headless environments this may fail, so guard it
try:
    if 'ax' in locals() and ax is not None:
        plt.show()
    else:
        plt.close()
except Exception:
    # ensure figure closed if show fails
    try:
        plt.close()
    except Exception:
        pass

# create a small CSV indicating the run completed and basic metadata (always attempt this)
try:
    meta = {
        'completed_at': [datetime.datetime.now().isoformat()],
        'combined_rows': [len(combined)],
        'combined_columns': [len(combined.columns)],
        'combined_csv': [output_file if 'output_file' in locals() else ''],
        'plot_png': [plot_path if 'plot_path' in locals() else ''],
    }
    meta_df = pd.DataFrame(meta)
    done_file = os.path.join(output_dir, 'process_complete.csv')
    meta_df.to_csv(done_file, index=False)
    print(f"Completion CSV saved to {done_file}")
except Exception as e:
    print(f"Failed to write completion CSV: {e}")