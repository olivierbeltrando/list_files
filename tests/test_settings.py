import unittest
from unittest.mock import MagicMock, patch

from storage_settings import StorageSettings
from test_gui import Value


class CredentialPickerTests(unittest.TestCase):
    def editor(self):
        editor = object.__new__(StorageSettings)
        editor.secrets = {'main': {'user': 'alice', 'password': 'secret'}}
        editor.config = {'networkStorages': [dict(type='smb', server='nas', folder='video', credName='main')]}
        editor.selected = {'Shares': 0, 'Credentials': 'main'}
        editor.forms = {
            'Shares': (MagicMock(), {name: Value(value) for name, value in
                                    dict(server='nas', folder='video', credName='main', networkName='WORKGROUP').items()}),
            'Credentials': (MagicMock(), {name: Value(value) for name, value in
                                         dict(name='main', user='alice', password='secret').items()})}
        editor.credential_picker = MagicMock()
        return editor

    def test_picker_refreshes_and_chooses_valid_credential(self):
        editor = self.editor()
        variable = editor.forms['Shares'][1]['credName']
        variable.set('typo')
        editor.refresh_credentials()
        editor.credential_picker.__setitem__.assert_called_with('values', ['main'])
        self.assertEqual(variable.get(), 'main')
        editor.secrets = {}
        editor.refresh_credentials()
        self.assertEqual(variable.get(), '')

    def test_rename_updates_picker_current_form_and_saved_shares(self):
        editor = self.editor()
        editor.forms['Credentials'][1]['name'].set('renamed')
        editor.apply('Credentials')
        self.assertEqual(list(editor.secrets), ['renamed'])
        self.assertEqual(editor.config['networkStorages'][0]['credName'], 'renamed')
        self.assertEqual(editor.forms['Shares'][1]['credName'].get(), 'renamed')
        editor.credential_picker.__setitem__.assert_called_with('values', ['renamed'])

    def test_adding_credential_refreshes_options_without_losing_selection(self):
        editor = self.editor()
        editor.selected['Credentials'] = None
        editor.forms['Credentials'][1]['name'].set('second')
        editor.apply('Credentials')
        editor.credential_picker.__setitem__.assert_called_with('values', ['main', 'second'])
        self.assertEqual(editor.forms['Shares'][1]['credName'].get(), 'main')

    def test_deleting_unused_credential_removes_it_from_picker(self):
        editor = self.editor()
        editor.secrets['unused'] = {'user': 'bob', 'password': ''}
        editor.selected['Credentials'] = 'unused'
        editor.forms['Shares'][1]['credName'].set('unused')
        editor.delete('Credentials')
        self.assertEqual(editor.forms['Shares'][1]['credName'].get(), 'main')
        editor.credential_picker.__setitem__.assert_called_with('values', ['main'])


if __name__ == '__main__':
    unittest.main()
