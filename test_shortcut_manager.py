import unittest
from shortcut_manager import assignment_request

class ShortcutManagerTests(unittest.TestCase):
    def test_new_binding_request_preserves_identity(self):
        request = assignment_request('SUPER+CTRL', {'key':'K','editable':True,'state':'free'},
                                     {'id':'action-test','selectionKind':'action'}, 'Title', '', False)
        self.assertEqual(request['targetModifiers'], ['SUPER','CTRL'])
        self.assertEqual(request['selectionId'], 'action-test')
        self.assertEqual(request['targetBindingId'], '')
        self.assertFalse(request['confirmReplace'])

    def test_replacement_requires_explicit_confirmation(self):
        option = dict(key='K',editable=True,state='assigned',bindingId='old-binding')
        action = dict(id='next',kind='command')
        with self.assertRaises(ValueError):
            assignment_request('SUPER',option,action,'','',False)
        request = assignment_request('SUPER',option,action,'','--flag',True)
        self.assertEqual(request['targetBindingId'],'old-binding')
        self.assertEqual(request['customArguments'],'--flag')

    def test_uneditable_binding_and_missing_selection_rejected(self):
        with self.assertRaises(ValueError):
            assignment_request('SUPER',dict(key='K',editable=False),dict(id='next'),'','',True)
        with self.assertRaises(ValueError):
            assignment_request('SUPER',{},None,'','',False)
