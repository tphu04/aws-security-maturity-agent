def render_template(template: dict, context: dict):
    """
    Replace {{var}} recursively in params_template.
    """
    def replace(value):
        if isinstance(value, str):
            for k, v in context.items():
                value = value.replace(f"{{{{{k}}}}}", str(v))
            return value
        elif isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [replace(v) for v in value]
        return value

    return replace(template)
