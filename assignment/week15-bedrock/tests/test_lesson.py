import copy
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock,patch
from botocore.session import Session
from botocore.validate import validate_parameters
from lab import cli,config,documents
from lab.aws import session_for
from lab.iam import policies
from lab.lesson import generate,retrieve,rag
from lab.storage import sync

CONFIG={'region':'ap-northeast-2','profile':'offline-fixture','account_id':'000000000000',
        'suffix':'test01','bucket':'keulkeul-bedrock-000000000000-test01',
        'vector_bucket':'keulkeul-bedrock-000000000000-test01','vector_index':'documents',
        'service_role':'KeulkeulBedrockKB-test01','knowledge_base_id':'ABCDEF1234',
        'data_source_id':'ABCDEF5678','model_id':'apac.amazon.nova-lite-v1:0'}


def validate(service,operation,request):
    validate_parameters(request,Session().get_service_model(service).operation_model(operation).input_shape)


class Runtime:
    def __init__(self,answer='OFFLINE_FIXTURE',stop='end_turn'):
        self.requests=[];self.answer=answer;self.stop=stop
    def converse(self,**request):
        validate('bedrock-runtime','Converse',request);self.requests.append(request)
        return {'output':{'message':{'role':'assistant','content':[{'text':self.answer}]}},
                'usage':{'inputTokens':25,'outputTokens':7,'totalTokens':32},'stopReason':self.stop}


class Retriever:
    def __init__(self,items=None):
        self.requests=[];self.items=items or []
    def retrieve(self,**request):
        validate('bedrock-agent-runtime','Retrieve',request);self.requests.append(request)
        return {'retrievalResults':self.items}


def chunk(text='OFFLINE_FIXTURE',doc_id='lab-guide-v1'):
    return {'content':{'text':text,'type':'TEXT'},'metadata':{'doc_id':doc_id},'score':0.7,
            'location':{'s3Location':{'uri':'s3://fixture/docs/lab-guide.txt'}}}


class LessonTests(unittest.TestCase):
    def test_generate_without_kb_uses_converse_and_actual_fields(self):
        c={**CONFIG,'knowledge_base_id':'','data_source_id':''};runtime=Runtime(stop='max_tokens')
        out=generate(c,runtime,'문서 검색을 설명해 줘',max_tokens=64)
        self.assertEqual(out['usage']['outputTokens'],7)
        self.assertEqual(out['stop_reason'],'max_tokens')
        self.assertEqual(out['calls'],{'retrieve':0,'converse':1})
        self.assertEqual(json.loads(runtime.requests[0]['messages'][0]['content'][0]['text'])['evidence'],[])

    def test_max_tokens_changes_only_intended_request_field(self):
        runtime=Runtime();generate(CONFIG,runtime,'same',max_tokens=64);generate(CONFIG,runtime,'same',max_tokens=256)
        one,two=copy.deepcopy(runtime.requests)
        self.assertEqual(one.pop('inferenceConfig')['maxTokens'],64)
        self.assertEqual(two.pop('inferenceConfig')['maxTokens'],256)
        self.assertEqual(one,two)

    def test_invalid_generation_settings_do_not_call_model(self):
        runtime=Runtime()
        for values in [{'max_tokens':0},{'max_tokens':True},{'temperature':float('nan')},{'temperature':2}]:
            with self.assertRaises(ValueError):generate(CONFIG,runtime,'q',**values)
        self.assertEqual(runtime.requests,[])

    def test_empty_question_is_rejected(self):
        with self.assertRaises(ValueError):generate(CONFIG,Runtime(),'  ')

    def test_retrieve_has_filter_and_deduplicates(self):
        retriever=Retriever([chunk(),chunk(),chunk('second')]);out=retrieve(CONFIG,retriever,'q',top_k=3)
        self.assertEqual(len(out['evidence']),2)
        request=retriever.requests[0]['retrievalConfiguration']['vectorSearchConfiguration']
        self.assertEqual(request['numberOfResults'],3)
        self.assertEqual(request['filter']['equals']['key'],'doc_id')
        self.assertEqual(out['calls']['converse'],0)

    def test_top_k_is_maximum_and_original_text_length_retained(self):
        out=retrieve(CONFIG,Retriever([chunk('x'*6000),chunk('second')]),'q',top_k=1)
        self.assertEqual(len(out['evidence']),1)
        self.assertEqual(len(out['evidence'][0]['text']),4500)
        self.assertEqual(out['evidence'][0]['original_chars'],6000)

    def test_invalid_metadata_rejected(self):
        with self.assertRaises(ValueError):retrieve(CONFIG,Retriever([chunk(doc_id='wrong')]),'q')

    def test_invalid_top_k_does_not_call_retriever(self):
        retriever=Retriever()
        for k in [0,11,True]:
            with self.assertRaises(ValueError):retrieve(CONFIG,retriever,'q',top_k=k)
        self.assertEqual(retriever.requests,[])

    def test_rag_passes_actual_retrieved_text_with_same_system(self):
        runtime=Runtime('근거 [D1]');retriever=Retriever([chunk('actual test evidence')])
        generate(CONFIG,runtime,'q');out=rag(CONFIG,retriever,runtime,'q')
        self.assertEqual(runtime.requests[0]['system'],runtime.requests[1]['system'])
        payload=json.loads(runtime.requests[1]['messages'][0]['content'][0]['text'])
        self.assertEqual(payload['evidence'][0]['text'],'actual test evidence')
        self.assertEqual(out['calls'],{'retrieve':1,'converse':1})

    def test_no_evidence_skips_generation(self):
        runtime=Runtime();out=rag(CONFIG,Retriever(),runtime,'q')
        self.assertEqual(out['status'],'no_evidence');self.assertEqual(runtime.requests,[])

    def test_invalid_rag_settings_do_not_retrieve(self):
        retriever=Retriever()
        with self.assertRaises(ValueError):rag(CONFIG,retriever,Runtime(),'q',max_tokens=0)
        self.assertEqual(retriever.requests,[])

    def test_nonexistent_reference_detected(self):
        out=rag(CONFIG,Retriever([chunk()]),Runtime('답변 [D99]'),'q')
        self.assertEqual(out['status'],'invalid_citations')

    def test_account_and_root_guard(self):
        for identity in [{'Account':'999999999999','Arn':'arn:aws:iam::999999999999:user/test'},
                         {'Account':CONFIG['account_id'],'Arn':'arn:aws:iam::000000000000:root'}]:
            with patch('lab.aws.boto3.Session') as factory:
                factory.return_value.client.return_value.get_caller_identity.return_value=identity
                with self.assertRaises(ValueError):session_for(CONFIG)

    def test_policy_scope_and_sizes(self):
        generated=policies(CONFIG)
        self.assertIn('/docs/*',json.dumps(generated['kb-service-access.json']))
        self.assertNotIn('/papers/',json.dumps(generated))
        for p in generated.values():self.assertLess(len(json.dumps(p,separators=(',',':'))),6144)

    def test_create_index_permission_targets_index_not_bucket(self):
        # AWS S3 Vectors authorizes CreateIndex against an Index resource.
        statements=policies(CONFIG)['01-storage-setup.json']['Statement']
        create=[s for s in statements if 's3vectors:CreateIndex' in s['Action']]
        self.assertEqual(len(create),1)
        target=(f"arn:aws:s3vectors:{CONFIG['region']}:{CONFIG['account_id']}:"
                f"bucket/{CONFIG['vector_bucket']}/index/documents")
        self.assertEqual(create[0]['Effect'],'Allow')
        self.assertEqual(create[0]['Resource'],target)
        for statement in statements:
            if statement['Resource']==target.rsplit('/index/',1)[0]:
                self.assertNotIn('s3vectors:CreateIndex',statement['Action'])

    def test_sync_failed_documents_is_not_success(self):
        agent=MagicMock();agent.start_ingestion_job.return_value={'ingestionJob':{
            'status':'COMPLETE','statistics':{'numberOfDocumentsFailed':1}}}
        with self.assertRaises(ValueError):sync(CONFIG,agent)

    def test_upload_expected_owner_and_two_objects(self):
        s3=MagicMock();documents.upload(CONFIG,s3)
        self.assertEqual(s3.put_object.call_count,2)
        for call in s3.put_object.call_args_list:
            validate('s3','PutObject',call.kwargs)
            self.assertEqual(call.kwargs['ExpectedBucketOwner'],CONFIG['account_id'])
            self.assertTrue(call.kwargs['Key'].startswith('docs/'))

    def test_init_and_plans_do_not_create_aws_session(self):
        with tempfile.TemporaryDirectory() as folder:
            task=Path(folder);shutil.copy(config.ROOT/'config.example.json',task/'config.example.json')
            with patch.object(config,'ROOT',task),patch('lab.iam.ROOT',task),patch('lab.aws.boto3.Session',side_effect=AssertionError('AWS forbidden')):
                with redirect_stdout(io.StringIO()):
                    c=config.init_config(CONFIG['account_id'],'test01','offline-fixture')
                    self.assertFalse(c['knowledge_base_id'])
                    for args in [['plan'],['prepare'],['upload']]:
                        with patch('sys.argv',['lab.cli',*args]):self.assertEqual(cli.main(),0)
            c['bucket']='shared-bucket';(task/'config.json').write_text(json.dumps(c))
            with self.assertRaises(ValueError):config.load_config(task/'config.json')


if __name__=='__main__':unittest.main()
