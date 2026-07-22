import importlib
import os
import sys

sys.path.insert(0, r'd:\Offline')
print('cwd', os.getcwd())
mod = importlib.import_module('translation_module.nllb_eval_translator')
print('module', mod)
print('file', mod.__file__)
print('attrs', [name for name in ('NLLBSubtitleTranslator', 'NLLBTranslationError', 'NLLBTranslationResult') if hasattr(mod, name)])
print('dict has', 'NLLBSubtitleTranslator' in mod.__dict__)
print('class object', mod.__dict__.get('NLLBSubtitleTranslator'))
import translation_module
print('package has attr', hasattr(translation_module, 'NLLBSubtitleTranslator'))
print('package attr', getattr(translation_module, 'NLLBSubtitleTranslator', None))
