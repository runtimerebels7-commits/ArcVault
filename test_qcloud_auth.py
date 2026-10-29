from qpiai_quantum import QpiAIQuantumAuth as Auth

api_key = input("Enter your QCloud API key: ").strip()

Auth.login(api_key)
print("API key valid:", Auth.verify_api_key())