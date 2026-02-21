# FormatEx Python SDK

Official Python client for the FormatEx LaTeX-to-PDF API.

## Installation

```bash
pip install formatex
```

## Quick Start

```python
from formatex import FormatExClient

client = FormatExClient("fx_your_api_key")

# Basic compile
result = client.compile(r"\documentclass{article}\begin{document}Hello\end{document}")
with open("output.pdf", "wb") as f:
    f.write(result.pdf)

# Smart compile (auto-detect engine + auto-fix)
result = client.compile_smart(r"\documentclass{article}\begin{document}Hello\end{document}")

# Compile directly to file
client.compile_to_file(
    r"\documentclass{article}\begin{document}Hello\end{document}",
    "output.pdf",
    smart=True,
)

# Check syntax (free, no quota cost)
check = client.check_syntax(r"\documentclass{article}\begin{document}\end{document}")
print(check.valid, check.errors)

# Usage stats
usage = client.get_usage()
print(f"{usage.compilations_used}/{usage.compilations_limit} compilations this month")
```

## Engines

```python
result = client.compile(latex, engine="xelatex")  # Unicode + modern fonts
result = client.compile(latex, engine="lualatex")  # Lua scripting
result = client.compile(latex, engine="latexmk")   # Auto multi-pass
```

## Error Handling

```python
from formatex import (
    FormatExClient,
    AuthenticationError,
    CompilationError,
    RateLimitError,
    PlanLimitError,
)

client = FormatExClient("fx_your_api_key")

try:
    result = client.compile(latex)
except AuthenticationError:
    print("Invalid API key")
except CompilationError as e:
    print(f"Compilation failed: {e}")
    print(f"Compiler log: {e.log}")
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except PlanLimitError:
    print("Plan limit exceeded, upgrade at https://formatex.com/pricing")
```

## Self-Hosted

```python
client = FormatExClient("fx_key", base_url="https://formatex.your-company.com")
```

## Context Manager

```python
with FormatExClient("fx_key") as client:
    result = client.compile(latex)
```
