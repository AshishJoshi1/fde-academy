# Parallel tool calls

When a question needs several lookups that don't depend on each other, the model asks for all of them in one response. Here you answer three `tool_use` blocks at once, measure what turning that off costs, and handle a lookup that fails with `is_error`. The **Timeline**, **Messages** and **Mock API** panels on the right show each turn, and the **Meridian data** page in the top bar has every record the mock API serves.
