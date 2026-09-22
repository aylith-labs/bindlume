import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import shortcut_sets
class CustomSetRemovalTests(unittest.TestCase):
 def test_only_reviewed_custom_file_can_be_trashed(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(shortcut_sets,'user_directory',return_value=Path(directory)):
   path=shortcut_sets.create_template();data=shortcut_sets.read(path)
   with patch.dict(shortcut_sets.CATALOG,{data['name']:data},clear=True),patch('gi.repository.Gio.File.new_for_path') as file:
    before=path.read_bytes()
    shortcut_sets.remove_custom(data['name'],before)
    file.assert_called_once_with(str(path));file.return_value.trash.assert_called_once_with(None)
    file.reset_mock();path.write_bytes(before+b'\n')
    with self.assertRaises(ValueError):shortcut_sets.remove_custom(data['name'],before)
    file.assert_not_called()
    with self.assertRaises(ValueError):shortcut_sets.remove_custom('Omarchy',before)
