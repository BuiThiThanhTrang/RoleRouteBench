"""Download only the public tokenizer needed for exact formal input budgeting."""
from pathlib import Path
import hashlib
import sys
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
TOKENIZER = PROJECT / '.cache/formal_runtime_tools/pythagoras-tokenizer.json'
SHA256 = 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4'
URL = 'https://huggingface.co/Pythagoras-LM/Pythagoras-Prover-4B/resolve/main/tokenizer.json'


def main():
    if TOKENIZER.exists():
        data = TOKENIZER.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError('Remote tokenizer changed; a reviewed version is required')
        TOKENIZER.parent.mkdir(parents=True, exist_ok=True)
        TOKENIZER.write_bytes(data)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Tokenizer cache does not match the configured checksum')
    from routing_benchmark.v4.execution.formal_actor import load_tokenizer, TokenizerSetupError
    try:
        tokenizer = load_tokenizer(str(TOKENIZER), SHA256)
    except TokenizerSetupError as error:
        raise SystemExit(str(error)) from None
    import tokenizers
    print('Pinned tokenizer ready:', TOKENIZER)
    print('Python:', sys.executable)
    print('tokenizers:', tokenizers.__version__)
    print('Lean tokenization smoke:', len(tokenizer.encode('by\n  rfl', add_special_tokens=False).ids), 'tokens')


if __name__ == '__main__':
    main()
