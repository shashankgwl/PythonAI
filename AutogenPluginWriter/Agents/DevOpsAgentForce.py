import json
from autogen import ConversableAgent, register_function
from Prompts import *  # Import all prompts
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

class DevOpsAgentForce:
    def __init__(self):
        self.key = self.read_secrets_file('OpenApiKey')
        self.ai_search_agent = ConversableAgent(
            name="AI_SEARCH_GENERATOR",
            llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": self.key}]},
            system_message=JSON_GENERATOR_PROMPT,
            human_input_mode="NEVER",
        )
        self.search_execution_agent = ConversableAgent(
            name="AI_SEARCH_EXECUTION",
            llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": self.key}]},
            system_message=JSON_EXECUTOR_PROMPT,
            human_input_mode="NEVER"
        )
        self.starting_agent = ConversableAgent(
            name="BobbyTheHuman",
            code_execution_config=False,
            human_input_mode="NEVER",
            system_message=STARTER_AGENT_PROMPT,
        )
        self.summary_agent = ConversableAgent(
            name="Summerizer",
            code_execution_config=False,
            llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": self.key}]},
            human_input_mode="NEVER",
            system_message=SUMMARY_AGENT_PROMPT,
        )
        register_function(
            self.search_azure_ai,
            caller=self.search_execution_agent,
            executor=self.starting_agent,
            name="SearchAzureAi",
            description="This tool executes the azure AI search JSON.",
        )

    def read_secrets_file(self, key):
        with open(r".\Agents\keys\keys.json") as f:
            data = json.load(f)
            return data[key]

    def search_azure_ai(self, search_json: str):
        ai_search_details = self.read_secrets_file('AzureSearch')

        search_client = SearchClient(
            endpoint=ai_search_details['Endpoint'],
            index_name=ai_search_details['Index'],
            credential=AzureKeyCredential(ai_search_details['Key'])
        )

        if isinstance(search_json, str):
            search_json = json.loads(search_json)

        search_text = search_json["search"]
        search_filter = search_json.get("filter")
        search_select = search_json.get("select")
        search_top = search_json.get("top")

        results = search_client.search(
            search_text=search_text,
            filter=search_filter,
            select=search_select,
            top=search_top,
        )

        formatted_results = "\n\n".join(
            [f"Score: {r['@search.score']}\n{r}" for r in results]
        )

        return formatted_results if formatted_results else "No results found."

    def process_query(self, user_query):
        chat_result = self.starting_agent.initiate_chats([
            {
                "recipient": self.ai_search_agent,
                "message": user_query,
                "max_turns": 1,
                "summary_method": "last_msg",
                "wait_for_response": True,
            },
            {
                "recipient": self.search_execution_agent,
                "message": "This is the JSON query to be executed",
                "max_turns": 2,
                "summary_method": "last_msg",
                "wait_for_response": True,
            }
        ])

        last_summary = user_query + "\n" + chat_result[1].summary
        response = self.summary_agent.generate_reply(messages=[{"content": last_summary, "role": "user"}])
        print("Response from summary agent: ", response)
        return response


# Example usage:
if __name__ == "__main__":
    agent = DevOpsAgentForce()
    user_query = input("Enter your query: ")
    agent.process_query(user_query)
