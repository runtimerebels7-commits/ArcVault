
import os

from qpiai_quantum import JobManager, QpiAIQuantumAuth

# Read the API key from an environment variable.
api_key = os.getenv("QCLOUD_API_KEY")

if not api_key:
    raise RuntimeError(
        "QCLOUD_API_KEY is missing. Set it in PowerShell before running this file."
    )

# Authenticate in this Python process.
auth = QpiAIQuantumAuth()
print("Logging in to QpiAI...")

try:
    print("Login result:", auth.login(api_key))
    print("API key valid:", auth.verify_api_key())

    # Create the job manager after authentication.
    job_manager = JobManager()

    qasm_circuit = """
OPENQASM 2.0;
include "qelib1.inc";

qreg q[1];
creg c[1];

h q[0];
measure q[0] -> c[0];
"""

    print("\nSubmitting test circuit to QpiAI...")

    result = job_manager.submit_and_wait_for_results_qasm(
        qasm_circuit,
        experiment_name="Default Experiment",
        shots=100,
        device_name="QpiAI-QSV-Simulator",
        circuit_name="arcvault_connection_test",
        timeout=120,
    )

    print("\nJob result:")
    print(result)

except Exception as error:
    print("\nQpiAI test failed.")
    print(type(error).__name__ + ":", error)