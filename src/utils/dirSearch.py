import os
from pathlib import Path
from loguru import logger as log
from config.config import SWASS_PATH_PATTERN


def find_seewo_resources_dir() -> str | None:
    log.info(f"尝试查找 SeewoServiceAssistant 安装目录, 匹配: {SWASS_PATH_PATTERN}")

    try:
        drive, pattern_part = os.path.splitdrive(SWASS_PATH_PATTERN)
        base_path = Path(drive + os.path.sep)
        pattern_glob = pattern_part.lstrip(os.path.sep)

        matches = list(base_path.glob(pattern_glob))

    except Exception as e:
        log.error(f"安装目录查找时发生错误: {e}")
        matches = []

    if not matches:
        log.error("未能找到希沃管家的安装目录。")
        log.error(
            "请确认已正确安装希沃管家, 如果你确定这是管理工具的问题, 请提交 Issue: https://github.com/blingbling-bow/HugoAura-Install/issues"
        )
        return None
    elif len(matches) > 1:
        log.warning(f"找到了多个匹配的目录: {[str(p) for p in matches]}")
        found_path = str(matches[-1])
        log.info(f"默认使用最后一个匹配的目录: {found_path}")
    else:
        found_path = str(matches[0])
        log.info(f"匹配成功, 希沃管家安装目录: {found_path}")

    if os.path.isdir(found_path):
        return found_path
    else:
        log.error(f"匹配过程中发生异常, ({found_path}) 不是一个合法的文件夹。")
        return None
