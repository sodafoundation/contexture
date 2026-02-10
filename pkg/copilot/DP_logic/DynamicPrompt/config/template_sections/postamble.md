Steps to Follow:

Step 1: Analyze the input text to understand the full context of the user's metric query request. Strip out any irrelevant formatting or noise.

Step 2: Determine the "type" of query being requested. Valid types include: `range`, `instant`, `error`.

Step 3: Use the `current_time` value as the starting point for calculating the `start`, `stop`, and `step` values. Always return these values in RFC 3339 format. 
`current_time` = {{current_time}}

Step 4: Based on the type, determine the other values apart from the query you need to find. The other values you need are given below:
  - For `range`: `start`, `stop`, and `step` values
  - For `instant`: `time` (optional; if not specified, assume to be `current_time`)
  - For `error`: `message` which is just the human-readable error message

  Categories of Queries:
1. Point-in-time metric (e.g., "CPU usage right now", "current memory consumption")-> Use `instant query`.
2. Time series over a period (e.g., "CPU usage over the past hour", "memory trend over the last week") -> Use `range query`.

Step 5: Create the core `query` expression. This is the PromQL string. If necessary, build the query using aggregation operators, functions, or vector selectors, based on what the input text describes. Explicitly explain how you construct this expression.

Step 6: Output ONLY the PromQL query expression inside a promql markdown code block.
The code block must contain the actual executable PromQL query you generated - nothing else.

IMPORTANT: 
- Do NOT include square brackets, angle brackets, placeholder text, comments (using #), or any descriptive text inside the code block.
- Do NOT add explanatory comments after the query.
- The query must be syntactically valid and executable as-is.
- PromQL does NOT support comments - do not use # symbols in the query.
- Do not ask the user for clarification or additional details. Always infer the best possible query and format.
- The PromQL query must be syntactically valid and ready to execute directly against Prometheus.

Take a deep breath and work on this problem step by step.