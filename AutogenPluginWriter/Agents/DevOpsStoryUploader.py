from bs4 import BeautifulSoup
import html
import base64
import json
import requests
import openai
class DevOpsStoryUploader():
    def __init__(self, name):
        self._name = name
        self.patToken = self.read_secrets_file("AdoDetails")["patToken"]
        self.aisearchkey = self.read_secrets_file("AzureSearch")["Key"]
        self.openApiKey = self.read_secrets_file("OpenApiKey")
        self.encoded_pat = base64.b64encode(f":{self.patToken}".encode()).decode()
        self.headers = {
            'Authorization': f'Basic {self.encoded_pat}',
            'Content-Type': 'application/json'
        }

        self.projectName = "<project_name>"
        self.organizationName = "<organization_name>"
        
        self.wiql_query = {
            "query": (
                f"SELECT [System.Id], [System.Title], [System.State], [System.AreaPath], [System.IterationPath], [Acceptance Criteria], [Approach] "
                f"FROM WorkItems "
                f"WHERE [System.TeamProject] = '<project>' "
                f"AND [System.WorkItemType] = 'User Story' "
                f"ORDER BY [System.Id] ASC"
            )
        }
        
        self.adoURL = self.read_secrets_file("AdoDetails")["ADOUrl"]
        self.pat_encoded = base64.b64encode(f":{self.patToken}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {self.pat_encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    def sendReply(self, message):
        return self.initiate_chat(self, messages=[{"role": "user", "content": message}])
    
    def getAdoUserStories(self):
        wiQlUrl = f"{self.adoURL}/{self.organizationName}/{self.projectName}/_apis/wit/wiql?api-version=7.1"
        response = requests.post(wiQlUrl, headers=self.headers, json=self.wiql_query)
        if response.status_code == 200:
            work_items = response.json()
            return [item['id'] for item in work_items.get('workItems', [])]
        return None
        
    def store_in_azure_ai(self, id):
        aisearchHeaders = {
            "Content-Type": "application/json",
            "api-key": self.aisearchkey
        }
        
        aaiendpoint = "https://adoaisearch.search.windows.net/indexes/workitems-index/docs/index?api-version=2024-07-01"
        adourl = f"{self.adoURL}/{self.organizationName}/{self.projectName}/_apis/wit/workitems/{id}?api-version=7.1"
        adoCommentEndpoint = f"{self.adoURL}/{self.organizationName}/{self.projectName}/_apis/wit/workitems/{id}/comments?api-version=7.1-preview.3"
        response = requests.get(adourl, headers=self.headers)
        adoComments = requests.get(adoCommentEndpoint, headers=self.headers)
        if adoComments.status_code == 200:
            comment_texts = [comment["text"] for comment in adoComments.json().get("comments", [])]
            merged_comments = " ".join([BeautifulSoup(comment, "html.parser").get_text() for comment in comment_texts])
        if response.status_code == 200:
            work_item = self.new_transform(response.json())
            for key, embed_key in {"AcceptanceCriteria": "AcceptanceCriteriaEmbds", "Title": "TitleEmbeds", "Approach": "ApproachEmbeds"}.items():
                if key in work_item["value"][0]:
                    work_item["value"][0][embed_key] = self.generate_embeddings(work_item["value"][0][key])
        
        
        comment_embds = self.generate_embeddings(merged_comments)
        
        work_item["value"][0]["CommentEmbeds"] = comment_embds
        work_item["value"][0]["MergedComments"] = merged_comments
        # Serialize work_item to a local file
            
        response = requests.post(aaiendpoint, headers=aisearchHeaders, json=work_item)
        if response.status_code in [200, 201]:
            print(f"Work item {id} stored successfully")
            return True
        else:
            print(f"Error storing work item {id}: {response.text}")
        return False
    
    def generate_embeddings(self, columnText):
        try:
            openai.api_key = self.openApiKey
            response = openai.embeddings.create(
                input=columnText,
                model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return None
    
    
    def new_transform(self, work_item):
    # Clean up field keys
        fields = {key.replace("System.", "").replace("Microsoft.VSTS.Scheduling.","").replace("Microsoft.VSTS.Common.", "").replace("CT_Agile.", ""): value 
                for key, value in work_item.get("fields", {}).items()}
        work_item["fields"] = fields

        # Define keys that require HTML parsing
        html_keys = {"AcceptanceCriteria", "Approach", "Description"}

        
        transformed = {
        "value": [{
            "@search.action": "upload",
            "id": str(work_item["id"]),
            "AreaPath": fields.get("AreaPath"),
            "TeamProject": fields.get("TeamProject"),
            "IterationPath": fields.get("IterationPath"),
            "WorkItemType": fields.get("WorkItemType"),
            "State": fields.get("State"),
            "Reason": fields.get("Reason"),
            "Title": fields.get("Title"),
            "SWAGEstimate": fields.get("SWAGEstimate"),
            "Description": html.escape(fields["Description"]) if "Description" in fields else None,
            "AcceptanceCriteria": html.escape(fields["AcceptanceCriteria"]) if "AcceptanceCriteria" in fields else None,
            "Approach": html.escape(fields["Approach"]) if "Approach" in fields else None,
            "StoryPoints": fields.get("StoryPoints"),
            "CreatedDate": fields.get("CreatedDate"),
            "ChangedDate": fields.get("ChangedDate"),
            "rev": work_item.get("rev", 0),
        }]
        }
        # Remove items with value None
        transformed["value"][0] = {k: v for k, v in transformed["value"][0].items() if v is not None}
        return transformed
    
    def read_secrets_file(self, key):
        with open(r".\Agents\keys\keys.json") as f:
            data = json.load(f)
            return data[key]


helper = DevOpsStoryUploader("DevOpsHelper")
try:
    userStories = helper.getAdoUserStories()
    if userStories:
        for i in range(max(10, len(userStories))):
            try:
                helper.store_in_azure_ai(userStories[i])
                #helper.store_in_azure_ai(126412)
            except Exception as e:
                print(f"Error storing work item {userStories[i]}: {e}")
except Exception as e:
    print(f"Error fetching user stories: {e}")
