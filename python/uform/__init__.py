from json import load
from os.path import join, exists
from typing import Dict, Optional, Tuple, Literal
from enum import Enum

from huggingface_hub import snapshot_download


class Modality(Enum):
    TEXT_ENCODER = "text_encoder"
    IMAGE_ENCODER = "image_encoder"
    VIDEO_ENCODER = "video_encoder"
    TEXT_DECODER = "text_decoder"


def normalize_modalities(modalities: Tuple[str, Modality]) -> Tuple[Modality]:
    if modalities is None:
        return (Modality.TEXT_ENCODER, Modality.IMAGE_ENCODER, Modality.TEXT_DECODER, Modality.VIDEO_ENCODER)

    return tuple(x if isinstance(x, Modality) else Modality(x) for x in modalities)


def get_checkpoint(
    model_name: str,
    modalities: Tuple[str, Modality],
    token: Optional[str] = None,
    format: Literal[".pt", ".onnx"] = ".pt",
) -> Tuple[str, Dict[Modality, str], Optional[str]]:
    """Downloads a model checkpoint from the Hugging Face Hub.

    :param model_name: The name of the model to download, like `unum-cloud/uform3-image-text-english-small`
    :param token: The Hugging Face API token, if required
    :param modalities: The modalities to download, like `("text_encoder", "image_encoder")`
    :param format: The format of the model checkpoint, either `.pt` or `.onnx`
    :return: A tuple of the config path, dictionary of paths to different modalities, and tokenizer path
    """

    modalities = normalize_modalities(modalities)

    # It is not recommended to use `.pth` extension when checkpointing models
    # because it collides with Python path (`.pth`) configuration files.
    merged_model_names = [x + format for x in ["torch_weight", "weight", "model"]]
    separate_modality_names = [(x.value if isinstance(x, Modality) else x) + format for x in modalities]
    config_names = ["torch_config.json", "config.json"]
    tokenizer_names = ["tokenizer.json"]

    # The download stats depend on the number of times the `config.json` is pulled
    # https://huggingface.co/docs/hub/models-download-stats
    model_path = snapshot_download(
        repo_id=model_name,
        token=token,
        allow_patterns=merged_model_names + separate_modality_names + config_names + tokenizer_names,
    )

    # Find the first name in `config_names` that is present
    config_path = None
    for config_name in config_names:
        if exists(join(model_path, config_name)):
            config_path = join(model_path, config_name)
            break

    # Same for the tokenizer
    tokenizer_path = None
    for tokenizer_name in tokenizer_names:
        if exists(join(model_path, tokenizer_name)):
            tokenizer_path = join(model_path, tokenizer_name)
            break

    # Ideally, we want to separately fetch all the models.
    # If those aren't available, aggregate separate modalities and merge them.
    modality_paths = None
    for file_name in merged_model_names:
        if exists(join(model_path, file_name)):
            modality_paths = join(model_path, file_name)
            break

    if modality_paths is None:
        modality_paths = {}
        for separate_modality_name in separate_modality_names:
            if exists(join(model_path, separate_modality_name)):
                modality_name, _, _ = separate_modality_name.partition(".")
                modality_paths[Modality(modality_name)] = join(model_path, separate_modality_name)

    return config_path, modality_paths, tokenizer_path


def get_model(
    model_name: str,
    *,
    token: Optional[str] = None,
    modalities: Optional[Tuple[str]] = None,
):
    from uform.torch_encoders import TextImageEncoder
    from uform.torch_processors import TorchProcessor

    config_path, modality_paths, tokenizer_path = get_checkpoint(model_name, token, modalities, format=".pt")
    modality_paths = (
        {k.value: v for k, v in modality_paths.items()} if isinstance(modality_paths, dict) else modality_paths
    )

    model = TextImageEncoder(config_path, modality_paths)
    processor = TorchProcessor(config_path, tokenizer_path)

    return model.eval(), processor


def get_model_onnx(
    model_name: str,
    *,
    device: Literal["cpu", "cuda"] = "cpu",
    token: Optional[str] = None,
    modalities: Optional[Tuple[str]] = None,
):
    from uform.onnx_encoders import TextImageEncoder
    from uform.numpy_processors import NumPyProcessor

    config_path, modality_paths, tokenizer_path = get_checkpoint(model_name, token, modalities, format=".onnx")
    modality_paths = (
        {k.value: v for k, v in modality_paths.items()} if isinstance(modality_paths, dict) else modality_paths
    )

    model = TextImageEncoder(config_path, modality_paths, device=device)
    processor = NumPyProcessor(config_path, tokenizer_path)

    return model, processor
