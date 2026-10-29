import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import make_web_standalone


class StandaloneAssetsTest(unittest.TestCase):
    def test_current_build_keeps_images_available_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(make_web_standalone, "DIST", Path(directory)):
                html = make_web_standalone.build().read_text(encoding="utf-8")
        self.assertTrue("图片已内联（完全离线）" in html)
        self.assertTrue('"/modules/honkai-star-rail/assets/' in html)

    def test_features_load_as_unmodified_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(make_web_standalone, "DIST", Path(directory)):
                html = make_web_standalone.build(with_theme=False).read_text(encoding="utf-8")
        self.assertTrue("loadStandaloneFeature" in html, "单文件缺少模块加载入口")
        self.assertFalse("const GT_FEATURE = {" in html, "配速模块仍以字符串替换导出")
        self.assertFalse("const GT_HERTA_FEATURE = (() =>" in html, "角色顶分仍以字符串替换导出")
        self.assertFalse("const GT_AHA_FEATURE = (() =>" in html, "阿哈模块仍以字符串替换导出")
