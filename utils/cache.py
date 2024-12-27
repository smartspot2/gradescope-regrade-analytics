import json
import os

from utils.types import LinkMap, RegradeInfoDict


def check_cache(cache_folder: str, course_id: str, assignment_id: str):
    """
    Check the cache folder to determine if the regrade request information has been cached.
    Returns the absolute cache file path if found; returns None otherwise.
    """
    cache_folder_path = os.path.abspath(cache_folder)
    if not os.path.exists(cache_folder_path):
        return None

    assert os.path.isdir(cache_folder_path), "Cache folder is not a valid directory"

    cache_file_name = f"{course_id}_{assignment_id}.json"

    for entry in os.scandir(cache_folder_path):
        if entry.is_file() and entry.name == cache_file_name:
            return entry.path

    # did not find the cache file
    return None


def load_cache(cache_file: str) -> tuple[RegradeInfoDict, LinkMap]:
    """
    Load `regrade_info` and `link_map` from the cache file.
    """

    with open(cache_file, "r", encoding="utf-8") as f:
        cached_json = json.load(f)

    regrade_info = cached_json["regrade_info"]
    link_map = cached_json["link_map"]

    return regrade_info, link_map


def save_cache(
    cache_folder: str,
    course_id: str,
    assignment_id: str,
    regrade_info: RegradeInfoDict,
    link_map: LinkMap,
):
    """
    Save `regrade_info` and `link_map` to the cache folder.
    """
    cache_folder_path = os.path.abspath(cache_folder)

    if not os.path.exists(cache_folder_path):
        # create the cache folder if it doesn't exist
        os.makedirs(cache_folder_path)

    assert os.path.isdir(cache_folder_path), "Cache folder is not a valid directory"

    cache_file_name = f"{course_id}_{assignment_id}.json"
    cache_file_path = os.path.join(cache_folder_path, cache_file_name)

    cached_json = {"regrade_info": regrade_info, "link_map": link_map}

    with open(cache_file_path, "w", encoding="utf-8") as f:
        json.dump(cached_json, f)
