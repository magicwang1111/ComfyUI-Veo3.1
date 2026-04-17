from .nodes import (
    NODE_PREFIX,
    PreviewVideoNode,
    Veo31ImageNode,
    Veo31TextNode,
)


def _node_name(label):
    return f"{NODE_PREFIX} {label}"


NODE_CLASS_MAPPINGS = {
    _node_name("Text-to-Video"): Veo31TextNode,
    _node_name("Image-to-Video"): Veo31ImageNode,
    _node_name("Preview Video"): PreviewVideoNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {key: key for key in NODE_CLASS_MAPPINGS}
