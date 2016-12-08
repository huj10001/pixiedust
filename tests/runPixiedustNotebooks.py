# -------------------------------------------------------------------------------
# Copyright IBM Corp. 2016
# 
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
# http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# -------------------------------------------------------------------------------
import os
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
from nbconvert.preprocessors.execute import CellExecutionError
import logging
from ipykernel.kernelspec import KernelSpecManager, write_kernel_spec
from jupyter_client.manager import KernelManager
from jupyter_client.kernelspec import NoSuchKernel
import shutil

__TEST_KERNEL_NAME__ = "PixiedustTravisTest"

logging.basicConfig(level=logging.DEBUG)

def createKernelSpecIfNeeded(kernelName):
    try:
        km = KernelManager(kernel_name=kernelName)
        km.kernel_spec
        return None
    except NoSuchKernel:
        sparkHome = os.environ["SPARK_HOME"]
        overrides={
            "argv": [
                "python",
                "-m",
                "ipykernel",
                "-f",
                "{connection_file}"
            ],
            "env": {
                "SCALA_HOME": "{0}".format(os.environ["SCALA_HOME"]),
                "SPARK_HOME": "{0}".format(sparkHome),
                "PYTHONPATH": "{0}/python/:{0}/python/lib/py4j-0.9-src.zip".format(sparkHome),
                "PYTHONSTARTUP": "{0}/python/pyspark/shell.py".format(sparkHome),
                "PYSPARK_SUBMIT_ARGS": "--driver-class-path {0}/data/libs/* --master local[10] pyspark-shell".format(os.path.expanduser('~')),
                "SPARK_DRIVER_MEMORY":"10G",
                "SPARK_LOCAL_IP":"127.0.0.1"
            }
        }
        path = write_kernel_spec(overrides=overrides)
        dest = KernelSpecManager().install_kernel_spec(path, kernel_name=kernelName, user=True)
        # cleanup afterward
        shutil.rmtree(path)
        return dest

class RestartKernelException(Exception):
    pass

class PixieDustTestExecutePreprocessor( ExecutePreprocessor ):
    def preprocess_cell(self, cell, resources, cell_index):
        beforeOutputs = cell.outputs
        skipCompareOutput = "#SKIP_COMPARE_OUTPUT" in cell.source
        try:
            cell, resources = super(PixieDustTestExecutePreprocessor, self).preprocess_cell(cell, resources, cell_index)
            for output in cell.outputs:
                if "text" in output and "restart kernel" in output["text"]:
                    print("restarting kernel...")
                    raise RestartKernelException()
            if not skipCompareOutput:
                self.compareOutputs(beforeOutputs, cell.outputs)
            return cell, resources
        except CellExecutionError:
            cell.source="%pixiedustLog -l debug"
            cell, resources = super(PixieDustTestExecutePreprocessor, self).preprocess_cell(cell, resources, cell_index)
            print("An error occurred executing the last cell. Fetching pixiedust log...")
            print(cell.outputs[0].text)
            raise

    def compareOutputs(self, beforeOutputs, afterOutputs):
        if ( len(beforeOutputs) != len(afterOutputs)):
            raise CellExecutionError("Output do not match. Expected {0} got {1}".format(beforeOutputs, afterOutputs))

        for beforeOutput, afterOutput in list(zip(beforeOutputs,afterOutputs)):
            if len(beforeOutput) != len(afterOutput):
                raise CellExecutionError("Output do not match. Expected {0} got {1}".format(beforeOutputs, afterOutputs))
            for key in beforeOutput:
                if beforeOutput[key] != afterOutput[key]:
                    raise CellExecutionError("Output do not match for. Expected {0} got {1}".format(beforeOutput, afterOutput))

def runNotebook(path):
    ep = PixieDustTestExecutePreprocessor(timeout=3600, kernel_name= __TEST_KERNEL_NAME__)
    nb=nbformat.read(path, as_version=4)
    #set the kernel name to test
    nb.metadata.kernelspec.name=__TEST_KERNEL_NAME__
    try:
        ep.preprocess(nb, {'metadata':{'path': os.path.dirname(path)}})
    finally:
        dir = os.environ.get("PIXIEDUST_TEST_OUTPUT", os.path.expanduser('~') + "/pixiedust") + "/tests"
        if not os.path.exists(dir):
            os.makedirs( dir )
        nbformat.write(nb, dir + "/" + os.path.basename(path) + ".out")

if __name__ == '__main__':
    kernelPath = createKernelSpecIfNeeded(__TEST_KERNEL_NAME__)
    try:
        inputDir = os.environ.get("PIXIEDUST_TEST_INPUT", './tests')
        for path in os.listdir( inputDir ):
            if path.endswith(".ipynb"):
                print(path)
                try:
                    runNotebook(inputDir + "/" + path)
                except RestartKernelException:
                    runNotebook(inputDir + "/" + path)
    finally:
        if kernelPath:
            shutil.rmtree(kernelPath)