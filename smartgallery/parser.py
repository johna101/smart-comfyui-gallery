# Smart Gallery for ComfyUI - ComfyMetadataParser
# Advanced parser that traces the workflow graph to find real generation parameters.

from typing import Dict, Any
from smartgallery.utils import clean_prompt_text


class ComfyMetadataParser:
    """
    Advanced parser that traces the workflow graph to find real generation parameters.
    Updated to resolve links for Width, Height, and other linked numeric values.
    """
    def __init__(self, workflow_json: Dict):
        self.data = workflow_json

    def parse(self) -> Dict[str, Any]:
        """Main parsing method. Returns a standardized dictionary."""
        meta = {
            "seed": None, "steps": None, "cfg": None, "sampler": None,
            "scheduler": None, "model": None, "positive_prompt": "",
            "negative_prompt": "", "positive_prompt_clean": "",
            "width": None, "height": None, "loras": []
        }

        sampler_node_id = self._find_sampler_node()

        if sampler_node_id:
            self._extract_sampler_params(sampler_node_id, meta)
            self._extract_prompts_from_sampler(sampler_node_id, meta)
            self._extract_model_from_sampler(sampler_node_id, meta)
            self._extract_size_from_sampler(sampler_node_id, meta)

        self._fallback_scan(meta)

        if meta["positive_prompt"]:
            cleaned = clean_prompt_text(meta["positive_prompt"])
            meta["positive_prompt_clean"] = cleaned["text"]
            meta["loras"] = cleaned["loras"]

        if meta["negative_prompt"] == meta["positive_prompt"]:
            meta["negative_prompt"] = ""

        return meta

    def _find_sampler_node(self):
        """Finds the main KSampler node ID."""
        if not isinstance(self.data, dict): return None
        for node_id, node in self.data.items():
            if not isinstance(node, dict): continue
            class_type = node.get("class_type", "")
            if "KSampler" in class_type or "SamplerCustom" in class_type:
                return node_id
        return None

    def _get_real_value(self, value):
        """
        Follows links recursively to find the actual value.
        Improved to handle UI format where values are in widgets_values.
        """
        if not isinstance(value, list):
            return value

        try:
            source_id = str(value[0])
            if source_id in self.data:
                node = self.data[source_id]

                inputs = node.get("inputs", {})
                for key in ["value", "int", "float", "string", "text"]:
                    if key in inputs:
                        return self._get_real_value(inputs[key])

                widgets = node.get("widgets_values", [])
                if widgets and not isinstance(widgets[0], (list, dict)):
                    return widgets[0]

                if widgets and isinstance(widgets[0], list):
                    return self._get_real_value(widgets[0])
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        return None

    def _extract_size_from_sampler(self, node_id, meta):
        """Traces the latent image link to find dimensions."""
        inputs = self.data[node_id].get("inputs", {})
        found_size = False

        if "latent_image" in inputs:
            link = inputs["latent_image"]
            if isinstance(link, list):
                source_id = str(link[0])
                node = self.data.get(source_id, {})
                node_inputs = node.get("inputs", {})

                if "width" in node_inputs:
                    meta["width"] = self._get_real_value(node_inputs["width"])
                    found_size = True
                if "height" in node_inputs:
                    meta["height"] = self._get_real_value(node_inputs["height"])

        if not found_size:
            for n in self.data.values():
                if n.get("class_type") == "EmptyLatentImage":
                    meta["width"] = self._get_real_value(n.get("inputs", {}).get("width"))
                    meta["height"] = self._get_real_value(n.get("inputs", {}).get("height"))
                    break

    def _extract_sampler_params(self, node_id, meta):
        """Extracts simple scalar values from the Sampler, resolving links."""
        inputs = self.data[node_id].get("inputs", {})

        if "seed" in inputs: meta["seed"] = self._get_real_value(inputs["seed"])
        if "noise_seed" in inputs: meta["seed"] = self._get_real_value(inputs["noise_seed"])
        if "steps" in inputs: meta["steps"] = self._get_real_value(inputs["steps"])
        if "cfg" in inputs: meta["cfg"] = self._get_real_value(inputs["cfg"])
        if "sampler_name" in inputs: meta["sampler"] = self._get_real_value(inputs["sampler_name"])
        if "scheduler" in inputs: meta["scheduler"] = self._get_real_value(inputs["scheduler"])
        if "denoise" in inputs: meta["denoise"] = self._get_real_value(inputs["denoise"])

    def _extract_prompts_from_sampler(self, node_id, meta):
        """Traces 'positive' and 'negative' links to find text."""
        inputs = self.data[node_id].get("inputs", {})
        if "positive" in inputs:
            meta["positive_prompt"] = self._trace_text(inputs["positive"])
        if "negative" in inputs:
            meta["negative_prompt"] = self._trace_text(inputs["negative"])

    def _trace_text(self, link_info) -> str:
        """Recursive helper to find text content from a link."""
        if not isinstance(link_info, list): return ""
        source_id = str(link_info[0])
        if source_id not in self.data: return ""

        node = self.data[source_id]
        inputs = node.get("inputs", {})

        # Check common text input keys (varies by node type)
        for text_key in ("text", "prompt", "t5xxl"):
            if text_key in inputs:
                if isinstance(inputs[text_key], str):
                    return inputs[text_key]
                if isinstance(inputs[text_key], list):
                    return self._trace_text(inputs[text_key])

        if "conditioning" in inputs:
            return self._trace_text(inputs["conditioning"])

        widgets = node.get("widgets_values", [])
        for w in widgets:
            if isinstance(w, str) and len(w) > 5: return w

        return ""

    def _extract_model_from_sampler(self, node_id, meta):
        """Follows the model wire to find the Checkpoint name."""
        inputs = self.data[node_id].get("inputs", {})
        if "model" in inputs:
            model_link = inputs["model"]
            if isinstance(model_link, list):
                source_id = str(model_link[0])
                if source_id in self.data:
                    node = self.data[source_id]
                    if "ckpt_name" in node.get("inputs", {}):
                        meta["model"] = node["inputs"]["ckpt_name"]
                    elif "model" in node.get("inputs", {}) and isinstance(node["inputs"]["model"], list):
                        self._extract_model_from_sampler(source_id, meta)

    def _fallback_scan(self, meta):
        """Scans all nodes for specific types if direct tracing missed data."""
        if not isinstance(self.data, dict): return
        for node_id, node in self.data.items():
            if not isinstance(node, dict): continue
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})

            if meta["seed"] is None and class_type == "RandomNoise":
                if "noise_seed" in inputs: meta["seed"] = self._get_real_value(inputs["noise_seed"])

            if meta["cfg"] is None and "Guider" in class_type:
                if "cfg" in inputs: meta["cfg"] = self._get_real_value(inputs["cfg"])

            if meta["steps"] is None and "Scheduler" in class_type:
                if "steps" in inputs: meta["steps"] = self._get_real_value(inputs["steps"])
