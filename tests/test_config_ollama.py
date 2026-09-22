"""
Tests unitaires — Config et helpers Ollama.

Couvre :
  - Config.validate
  - Config.get_output_folder
  - Config.get_word_file_path
  - ollama_ocr._host_from_config

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_config_ollama.py -v
"""

import unittest
from pathlib import Path


from config import Config


# ══════════════════════════════════════════════════════════════════════
# 1. Config.validate
# ══════════════════════════════════════════════════════════════════════

class TestConfigValidate(unittest.TestCase):
    """Config.validate() détecte les configurations incohérentes."""

    def _patch(self, **kwargs):
        """Remplace temporairement des attributs Config pour un test."""
        originals = {k: getattr(Config, k) for k in kwargs}
        for k, v in kwargs.items():
            setattr(Config, k, v)
        return originals

    def _restore(self, originals):
        for k, v in originals.items():
            setattr(Config, k, v)

    def test_valid_default_config(self):
        """La configuration par défaut est valide."""
        self.assertTrue(Config.validate())

    def test_image_name_without_index_raises(self):
        """IMAGE_NAME_FORMAT sans {index} → ValueError."""
        orig = self._patch(IMAGE_NAME_FORMAT='bornier')
        try:
            with self.assertRaises(ValueError):
                Config.validate()
        finally:
            self._restore(orig)

    def test_image_name_with_index_ok(self):
        orig = self._patch(IMAGE_NAME_FORMAT='scan_{index:03d}')
        try:
            self.assertTrue(Config.validate())
        finally:
            self._restore(orig)

    def test_allowed_formats_none_ok(self):
        orig = self._patch(ALLOWED_FORMATS=None)
        try:
            self.assertTrue(Config.validate())
        finally:
            self._restore(orig)

    def test_allowed_formats_list_ok(self):
        orig = self._patch(ALLOWED_FORMATS=['jpg', 'png'])
        try:
            self.assertTrue(Config.validate())
        finally:
            self._restore(orig)

    def test_allowed_formats_string_raises(self):
        """ALLOWED_FORMATS doit être une liste ou None, pas une chaîne."""
        orig = self._patch(ALLOWED_FORMATS='jpg')
        try:
            with self.assertRaises(ValueError):
                Config.validate()
        finally:
            self._restore(orig)


# ══════════════════════════════════════════════════════════════════════
# 2. Config.get_output_folder
# ══════════════════════════════════════════════════════════════════════

class TestConfigGetOutputFolder(unittest.TestCase):
    """get_output_folder() retourne le bon chemin selon OUTPUT_BASE_PATH."""

    def _patch(self, **kwargs):
        originals = {k: getattr(Config, k) for k in kwargs}
        for k, v in kwargs.items():
            setattr(Config, k, v)
        return originals

    def _restore(self, originals):
        for k, v in originals.items():
            setattr(Config, k, v)

    def test_none_base_uses_cwd(self):
        """OUTPUT_BASE_PATH=None → chemin relatif au répertoire courant."""
        orig = self._patch(OUTPUT_BASE_PATH=None, IMAGES_FOLDER_NAME='TestDossier')
        try:
            folder = Config.get_output_folder()
            self.assertEqual(folder, Path.cwd() / 'TestDossier')
        finally:
            self._restore(orig)

    def test_explicit_base_path(self):
        """OUTPUT_BASE_PATH explicite → chemin composé."""
        orig = self._patch(
            OUTPUT_BASE_PATH=r'C:\Extractions',
            IMAGES_FOLDER_NAME='BORNIER_SET',
        )
        try:
            folder = Config.get_output_folder()
            self.assertEqual(folder, Path(r'C:\Extractions') / 'BORNIER_SET')
        finally:
            self._restore(orig)

    def test_returns_path_object(self):
        """La valeur retournée est un objet Path."""
        folder = Config.get_output_folder()
        self.assertIsInstance(folder, Path)

    def test_folder_name_appended(self):
        """Le nom du dossier d'images est bien appended."""
        orig = self._patch(OUTPUT_BASE_PATH=None, IMAGES_FOLDER_NAME='DOSSIER_X')
        try:
            folder = Config.get_output_folder()
            self.assertEqual(folder.name, 'DOSSIER_X')
        finally:
            self._restore(orig)


# ══════════════════════════════════════════════════════════════════════
# 3. Config.get_word_file_path
# ══════════════════════════════════════════════════════════════════════

class TestConfigGetWordFilePath(unittest.TestCase):
    """get_word_file_path() résout les chemins relatifs et absolus."""

    def _patch(self, **kwargs):
        originals = {k: getattr(Config, k) for k in kwargs}
        for k, v in kwargs.items():
            setattr(Config, k, v)
        return originals

    def _restore(self, originals):
        for k, v in originals.items():
            setattr(Config, k, v)

    def test_relative_path_resolved_from_cwd(self):
        orig = self._patch(WORD_FILE='mon_document.docx')
        try:
            result = Config.get_word_file_path()
            self.assertEqual(result, Path.cwd() / 'mon_document.docx')
        finally:
            self._restore(orig)

    def test_absolute_path_unchanged(self):
        abs_path = r'C:\Docs\fichier.docx'
        orig = self._patch(WORD_FILE=abs_path)
        try:
            result = Config.get_word_file_path()
            self.assertEqual(result, Path(abs_path))
        finally:
            self._restore(orig)

    def test_returns_path_object(self):
        result = Config.get_word_file_path()
        self.assertIsInstance(result, Path)


# ══════════════════════════════════════════════════════════════════════
# 4. ollama_ocr._host_from_config
# ══════════════════════════════════════════════════════════════════════

class TestHostFromConfig(unittest.TestCase):
    """_host_from_config() extrait le scheme://host:port de l'URL complète."""

    def setUp(self):
        from ollama_ocr import _host_from_config
        self._fn = _host_from_config

    def _patch_url(self, url):
        original = Config.OLLAMA_URL
        Config.OLLAMA_URL = url
        return original

    def _restore_url(self, original):
        Config.OLLAMA_URL = original

    def test_standard_url(self):
        orig = self._patch_url('http://localhost:11434/v1/chat/completions')
        try:
            host = self._fn()
            self.assertEqual(host, 'http://localhost:11434')
        finally:
            self._restore_url(orig)

    def test_custom_port(self):
        orig = self._patch_url('http://192.168.1.10:8080/api/chat')
        try:
            host = self._fn()
            self.assertEqual(host, 'http://192.168.1.10:8080')
        finally:
            self._restore_url(orig)

    def test_https_scheme(self):
        orig = self._patch_url('https://ollama.example.com/v1/completions')
        try:
            host = self._fn()
            self.assertEqual(host, 'https://ollama.example.com')
        finally:
            self._restore_url(orig)

    def test_no_path_url(self):
        """URL sans chemin → retourne l'URL telle quelle."""
        orig = self._patch_url('http://localhost:11434')
        try:
            host = self._fn()
            self.assertEqual(host, 'http://localhost:11434')
        finally:
            self._restore_url(orig)

    def test_returns_string(self):
        result = self._fn()
        self.assertIsInstance(result, str)

    def test_no_trailing_slash(self):
        orig = self._patch_url('http://localhost:11434/v1/chat/completions')
        try:
            host = self._fn()
            self.assertFalse(host.endswith('/'), "Pas de slash final")
        finally:
            self._restore_url(orig)


# ══════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
