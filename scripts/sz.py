#!/usr/bin/env python3
"""Code size stats: lines and tokens-per-line for .py / .ts / .tsx files."""
import itertools, os, sys, token, tokenize

TOKEN_WHITELIST = [token.OP, token.NAME, token.NUMBER, token.STRING]
CODE_EXTS = (".py", ".ts", ".tsx")
SKIP_DIR_NAMES = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "coverage", ".cursor", ".tox", ".mypy_cache", ".pytest_cache", ".next", ".nuxt"}

def is_docstring(t):
  return t.type == token.STRING and t.string.startswith('"""') and t.line.strip().startswith('"""')

def is_ts_token(line):
  stripped = line.strip()
  return len(stripped) and not stripped.startswith('//')

def load_gitignore_skip(base_path):
  skip = set()
  gitignore = os.path.join(base_path, ".gitignore")
  if not os.path.isfile(gitignore): return skip
  with open(gitignore) as f:
    for line in f:
      line = line.strip()
      if not line or line.startswith("#"): continue
      if line.startswith("!"): continue
      skip.add(line.rstrip("/"))
  return skip

def should_skip_dir(name, gitignore_skip):
  if name in SKIP_DIR_NAMES: return True
  return name in gitignore_skip or f"{name}/" in gitignore_skip

def iter_code_files(base_path):
  gitignore_skip = load_gitignore_skip(base_path)
  for path, dirnames, files in os.walk(base_path):
    dirnames[:] = [d for d in dirnames if not should_skip_dir(d, gitignore_skip)]
    for name in files:
      ext = os.path.splitext(name)[1]
      if ext not in CODE_EXTS: continue
      filepath = os.path.join(path, name)
      relfilepath = os.path.relpath(filepath, base_path).replace('\\', '/')
      parts = relfilepath.split("/")
      if any(should_skip_dir(p, gitignore_skip) for p in parts[:-1]): continue
      yield filepath, relfilepath, ext

def file_stats(filepath, ext):
  if ext in (".ts", ".tsx"):
    with open(filepath) as f:
      lines = [line.strip() for line in f.readlines()]
    token_count = sum(len(line.split()) for line in lines if is_ts_token(line))
    line_count = sum(1 for line in lines if is_ts_token(line))
  else:
    with tokenize.open(filepath) as f:
      tokens = [t for t in tokenize.generate_tokens(f.readline) if t.type in TOKEN_WHITELIST and not is_docstring(t)]
    token_count = len(tokens)
    line_count = len(set(x for t in tokens for x in range(t.start[0], t.end[0]+1)))
  return line_count, token_count

def gen_stats(base_path="."):
  base_path = os.path.abspath(base_path)
  table = []
  for filepath, relfilepath, ext in iter_code_files(base_path):
    line_count, token_count = file_stats(filepath, ext)
    if line_count > 0:
      table.append([relfilepath, line_count, token_count / line_count])
  return table

def gen_diff(table_old, table_new):
  table = []
  files_new = set(x[0] for x in table_new)
  files_old = set(x[0] for x in table_old)
  added, deleted, unchanged = files_new - files_old, files_old - files_new, files_new & files_old
  for file in added:
    s = next(x for x in table_new if x[0] == file)
    table.append([s[0], s[1], s[1], s[2], s[2]])
  for file in deleted:
    s = next(x for x in table_old if x[0] == file)
    table.append([s[0], 0, -s[1], 0, -s[2]])
  for file in unchanged:
    old = next(x for x in table_old if x[0] == file)
    new = next(x for x in table_new if x[0] == file)
    if new[1] != old[1] or new[2] != old[2]:
      table.append([new[0], new[1], new[1]-old[1], new[2], new[2]-old[2]])
  return table

def display_diff(diff): return "+"+str(diff) if diff > 0 else str(diff)

def format_row(cells, widths):
  return "  ".join(str(c).ljust(w) if i == 0 else str(c).rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))

def print_table(headers, rows, diff_mode=False):
  str_rows = []
  for row in rows:
    if diff_mode:
      str_rows.append([row[0], row[1], display_diff(row[2]), f"{row[3]:.1f}", display_diff(round(row[4], 1))])
    else:
      str_rows.append([row[0], row[1], f"{row[2]:.1f}"])
  all_rows = [headers] + str_rows
  widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]
  print(format_row(headers, widths))
  for row in str_rows:
    print(format_row(row, widths))

if __name__ == "__main__":
  if len(sys.argv) == 3:
    headers = ["Name", "Lines", "Diff", "Tokens/Line", "Diff"]
    table = gen_diff(gen_stats(sys.argv[1]), gen_stats(sys.argv[2]))
    diff_mode = True
  elif len(sys.argv) == 2:
    headers = ["Name", "Lines", "Tokens/Line"]
    table = gen_stats(sys.argv[1])
    diff_mode = False
  else:
    headers = ["Name", "Lines", "Tokens/Line"]
    table = gen_stats(".")
    diff_mode = False

  if table:
    if diff_mode:
      print("### Changes")
      print("```")
      print_table(headers, sorted(table, key=lambda x: -x[1]), diff_mode=True)
      print(f"\ntotal lines changed: {display_diff(sum(x[2] for x in table))}")
      print("```")
    else:
      print_table(headers, sorted(table, key=lambda x: -x[1]), diff_mode=False)
      print()
      groups = sorted([('/'.join(x[0].rsplit("/", 1)[0].split("/")[0:2]) if "/" in x[0] else ".", x[1], x[2]) for x in table])
      for dir_name, _group in itertools.groupby(groups, key=lambda x: x[0]):
        group = list(_group)
        print(f"{dir_name:40s} : {sum(x[1] for x in group):6d} in {len(group):2d} files")
      print()
      print(f"total lines: {sum(x[1] for x in table)}")
