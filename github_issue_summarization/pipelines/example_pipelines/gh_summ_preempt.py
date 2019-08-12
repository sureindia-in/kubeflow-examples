# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import kfp.dsl as dsl
import kfp.gcp as gcp
import kfp.components as comp


COPY_ACTION = 'copy_data'
TRAIN_ACTION = 'train'

copydata_op = comp.load_component_from_url(
  'https://raw.githubusercontent.com/amygdala/kubeflow-examples/preempt/github_issue_summarization/pipelines/components/t2t/datacopy_component.yaml'
  )

train_op = comp.load_component_from_url(
  'https://raw.githubusercontent.com/amygdala/kubeflow-examples/preempt/github_issue_summarization/pipelines/components/t2t/train_component.yaml'
  )

@dsl.pipeline(
  name='Github issue summarization',
  description='Demonstrate Tensor2Tensor-based training and TF-Serving'
)
def gh_summ(  #pylint: disable=unused-argument
  train_steps=2019300,
  project='YOUR_PROJECT_HERE',
  github_token='YOUR_GITHUB_TOKEN_HERE',
  working_dir='YOUR_GCS_DIR_HERE',
  checkpoint_dir='gs://aju-dev-demos-codelabs/kubecon/model_output_tbase.bak2019000',
  deploy_webapp='true',
  data_dir='gs://aju-dev-demos-codelabs/kubecon/t2t_data_gh_all/'
  ):


  copydata = copydata_op(
    working_dir=working_dir,
    data_dir=data_dir,
    checkpoint_dir=checkpoint_dir,
    model_dir='%s/%s/model_output' % (working_dir, '{{workflow.name}}'),
    action=COPY_ACTION
    ).apply(gcp.use_gcp_secret('user-gcp-sa'))

  train = train_op(
    working_dir=working_dir,
    data_dir=data_dir,
    checkpoint_dir=checkpoint_dir,
    model_dir='%s/%s/model_output' % (working_dir, '{{workflow.name}}'),
    action=TRAIN_ACTION, train_steps=train_steps,
    deploy_webapp=deploy_webapp
    ).apply(gcp.use_gcp_secret('user-gcp-sa'))

  serve = dsl.ContainerOp(
      name='serve',
      image='gcr.io/google-samples/ml-pipeline-kubeflow-tfserve',
      arguments=["--model_name", 'ghsumm-%s' % ('{{workflow.name}}',),
          "--model_path", '%s/%s/model_output/export' % (working_dir, '{{workflow.name}}')
          ]
      )
  train.after(copydata)
  serve.after(train)
  train.set_gpu_limit(4).apply(gcp.use_preemptible_nodepool()).set_retry(5)
  train.set_memory_limit('48G')

  with dsl.Condition(train.output == 'true'):
    webapp = dsl.ContainerOp(
        name='webapp',
        image='gcr.io/google-samples/ml-pipeline-webapp-launcher:v2ap',
        arguments=["--model_name", 'ghsumm-%s' % ('{{workflow.name}}',),
            "--github_token", github_token]

        )
    webapp.after(serve)


if __name__ == '__main__':
  import kfp.compiler as compiler
  compiler.Compiler().compile(gh_summ, __file__ + '.tar.gz')