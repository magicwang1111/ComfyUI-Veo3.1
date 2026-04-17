from .nodes import (
    NODE_PREFIX,
    PreviewVideoNode,
    Veo31FastImageNode,
    Veo31FastTextNode,
    Veo31ImageNode,
    Veo31TextNode,
)


def _node_name(label):
    return f"{NODE_PREFIX} {label}"


NODE_CLASS_MAPPINGS = {
    _node_name("veo-3.1-generate-preview (Text)"): Veo31TextNode,
    _node_name("veo-3.1-generate-preview (Image)"): Veo31ImageNode,
    _node_name("veo-3.1-fast-generate-preview (Text)"): Veo31FastTextNode,
    _node_name("veo-3.1-fast-generate-preview (Image)"): Veo31FastImageNode,
    _node_name("Preview Video"): PreviewVideoNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {key: key for key in NODE_CLASS_MAPPINGS}
