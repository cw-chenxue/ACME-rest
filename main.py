import os
import json
from typing import Union, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pprint import pprint

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.oauth2 import service_account
from google.cloud import compute_v1
from collections import defaultdict
from collections.abc import Iterable
from google.api_core.extended_operation import ExtendedOperation

class ListComputeEnginePayloadBody(BaseModel):
    project_id: str

class SetStatesPayloadBody(BaseModel):
    project_id: str
    zones: List[str]
    instances_names : List[str]

def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
):
    """
    Waits for the extended (long-running) operation to complete.

    If the operation is successful, it will return its result.
    If the operation ends with an error, an exception will be raised.
    If there were any warnings during the execution of the operation
    they will be printed to sys.stderr.

    Args:
        operation: a long-running operation you want to wait on.
        verbose_name: (optional) a more verbose name of the operation,
            used only during error and warning reporting.
        timeout: how long (in seconds) to wait for operation to finish.
            If None, wait indefinitely.

    Returns:
        Whatever the operation.result() returns.

    Raises:
        This method will raise the exception received from `operation.exception()`
        or RuntimeError if there is no exception set, but there is an `error_code`
        set for the `operation`.

        In case of an operation taking longer than `timeout` seconds to complete,
        a `concurrent.futures.TimeoutError` will be raised.
    """
    result = operation.result(timeout=timeout)

    if operation.error_code:
        print(
            f"Error during {verbose_name}: [Code: {operation.error_code}]: {operation.error_message}",
            file=sys.stderr,
            flush=True,
        )
        print(f"Operation ID: {operation.name}", file=sys.stderr, flush=True)
        raise operation.exception() or RuntimeError(operation.error_message)

    if operation.warnings:
        print(f"Warnings during {verbose_name}:\n", file=sys.stderr, flush=True)
        for warning in operation.warnings:
            print(f" - {warning.code}: {warning.message}", file=sys.stderr, flush=True)

    return result


app = FastAPI()

@app.get("/ping")
def ping():
    return {"key":"value"}


@app.get("/get_compute_engine")
def list_instances(
    project_id : str
):
    """
    Returns a dictionary of all instances present in a project, grouped by their zone.

    Args:
        project_id: project ID or project number of the Cloud project you want to use.
    Returns:
        A dictionary with zone names as keys (in form of "zones/{zone_name}") and
        iterable collections of Instance objects as values.
    """
    instance_client = compute_v1.InstancesClient()
    request = compute_v1.AggregatedListInstancesRequest()
    request.project = project_id
    # Use the `max_results` parameter to limit the number of results that the API returns per response page.
    request.max_results = 50
    agg_list = instance_client.aggregated_list(request=request)
    all_instances = {'VM instances':{}}
    for zone, response in agg_list:
        if response.instances:
            all_instances['VM instances'].update({zone: []})
            for instance in response.instances:
                all_instances['VM instances'][zone].append({
                        'instance_name' : instance.name, 
                        'status' : instance.status,
                        'machine_type' : instance.machine_type
                                            })
    return json.dumps(all_instances, sort_keys=True, indent=2)

@app.post("/set_state")
def set_instance_state(payload: SetStatesPayloadBody):
    project_id = payload.project_id
    zones = payload.zones
    instances_names = payload.instances_names

    instance_client = compute_v1.InstancesClient()
    request = compute_v1.AggregatedListInstancesRequest()
    request.project = project_id
    agg_list = instance_client.aggregated_list(request=request)

    for zone, response in agg_list:
        if response.instances:
            for instance in response.instances:
                current_zone = instance.zone.split('/')[-1]
                if instance.name in instances_names and current_zone in zones:
                    if instance.status == 'TERMINATED':
                        operation = instance_client.start(
                            project=project_id, zone=current_zone, instance=instance.name
                        )
                        wait_for_extended_operation(operation, "instance stopping")
                    elif instance.status == 'RUNNING':
                        operation = instance_client.stop(
                            project=project_id, zone=current_zone, instance=instance.name
                        )
                        wait_for_extended_operation(operation, "instance stopping")
    return {"results":"status set"}      


def main():
    os.system('uvicorn main:app --host 0.0.0.0 --port 8080')

if __name__ == "__main__":
    main()