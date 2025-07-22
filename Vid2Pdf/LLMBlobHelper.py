import base64
from azure.storage.blob import BlobServiceClient
from io import BytesIO
import logging
from collections import defaultdict
import os
from openai import AzureOpenAI

#LLM helper class to handle Azure Blob Storage and OpenAI interactions
class LLMBlobHelper:
    def __init__(self, connection_string, container_name, logging):
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        self.logger = logging
        self.previous_summary = ""
        self.combined_summary = ""
        self.final_summary = ""

        self.client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=os.environ.get("AifEndPoint"),
    api_key=os.environ.get("AifApiKey"),
)

    def list_blobs_under_folder(self, folder_prefix):
        """List blobs under any folder prefix."""
        if not folder_prefix.endswith('/'):
            folder_prefix += '/'
        return list(self.container_client.list_blobs(name_starts_with=folder_prefix))

    def extract_unique_guid_folders(self, parent_folder):
        """Extract unique GUID folders under the given parent folder."""
        blobs = self.list_blobs_under_folder(parent_folder)
        guid_folders = set()
        for blob in blobs:
            # blob.name example: wa.mp4/GUID/xyz.jpg
            parts = blob.name.split('/')
            if len(parts) >= 2 and parts[0] == parent_folder:
                guid_folders.add(parts[1])
        return list(guid_folders)
    
    def get_audio_txt_blob(self, parent_folder, guid_folder):
        """Retrieve the audio transcription text blob for a specific GUID folder."""
        blob_name = f"{parent_folder}/{guid_folder}/audio_text.txt"
        blob_client = self.container_client.get_blob_client(blob_name)
        try:
            download_stream = blob_client.download_blob()
            audio_text = download_stream.readall().decode('utf-8')
            return audio_text
        except Exception as e:
            print(f"Error retrieving audio transcription for {guid_folder}: {e}")
            return None

    def get_jpg_blobs(self, parent_folder, guid_folder):
        """List .jpg blobs inside a specific guid folder under the parent folder."""
        prefix = f"{parent_folder}/{guid_folder}/"
        return [
            blob.name for blob in self.container_client.list_blobs(name_starts_with=prefix)
            if blob.name.lower().endswith('.jpg')
        ]

    def jpg_to_base64(self, blob_name):
        logging.info(f"Converting {blob_name} to base64")
        blob_client = self.container_client.get_blob_client(blob_name)
        stream = BytesIO()
        download_stream = blob_client.download_blob()
        stream.write(download_stream.readall())
        stream.seek(0)
        encoded = base64.b64encode(stream.read()).decode('utf-8')
        return encoded

    def convert_all_jpgs(self, parent_folder):
        """Find all JPG files under all GUID folders inside `parent_folder`, convert them."""
        result = defaultdict(list)
        guid_folders = self.extract_unique_guid_folders(parent_folder)

        for guid_folder in guid_folders:
            jpg_blobs = self.get_jpg_blobs(parent_folder, guid_folder)
            for blob_name in jpg_blobs:
                base64_img = self.jpg_to_base64(blob_name)
                result[guid_folder].append(base64_img)
        
        return dict(result)

    def create_image_payload(self,base64_str_list):
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_str}"
                }
            }
            for b64_str in base64_str_list
        ]

    def batch_list(self,lst, batch_size):
        """Simple batching utility."""
        for i in range(0, len(lst), batch_size):
            yield lst[i:i + batch_size]
    
    def get_prompt(self, audiotext=None):
        agent_prompt = f"""
        You are an expert image summarizer. Your job is to look at images and describe or summarize them clearly and concisely. 
        If multiple images are provided, analyze them together and provide an integrated summary. The images provided to you will be
        in base64 format, and you will receive a list of images to analyze. They should mostly be teams meeting mp4 screenshots. Alternatively
        they can also be non meeting educational video screenshots, you should infer the context of the meeting from the images and then generate appropriate video summary.
        You also have the audio transcription text from the meeting, which is: {audiotext}
        Your task is to summarize the content of the images and the audio transcription in a coherent manner. Your response should be in
        HTML format, with the summary in a <p> tag, you should also include in the beggining about who was present in the meeting and what was the main topic of the meeting.
        the html format should have proper indentation and structure, with readable fonts and colors, stressing the important points.
        the flow of summary should include who said what, the main topics discussed, and any conclusions or action items that were agreed upon.
        """
        return agent_prompt if not audiotext else agent_prompt.format(audiotext=audiotext)
    
    def get_final_summary(self, previous_summary=None):
        """Get the final summary, either from the previous summary or the current one."""
        prompt = """
        You are an expert summarizer. You will be provided summaries of previously genereated videos. Your job is to take those previous summaries 
        and combine them into a single coherent summary.You should integrate the new summary with the previous one, and provide a final summary that is clear, concise, and coherent.
        """
        #make call to OpenAI with the previous summary
        if previous_summary:
            messages = [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": previous_summary
                }
            ]
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3
            )
            final_summary = response.choices[0].message.content
            return final_summary
     

    def call_aif(self, base64_images : dict, batchsize=5, mp4_folder=None, guid_file=None):
        audio_text = self.get_audio_txt_blob(mp4_folder, guid_file)
        for guid, images in base64_images.items():
            for batch in self.batch_list(images, batchsize):
                self.logger.info(f"Processing GUID: {guid} with {len(batch)} images")
                try:
                    payload = self.create_image_payload(batch)
                    messages = [
                        {
                            "role": "system",
                            "content": self.get_prompt(audiotext=audio_text)
                        },
                        {
                            "role": "user",
                            "content": [
                                *payload,  # list of 3 images in base64
                                {
                                    "type": "text",
                                    "text": "Please summarize what you can infer from these images."
                                }
                            ]
                        }
                    ]

                    if self.previous_summary:
                        messages.append({
                            "role": "user",
                            "content": f"Previously you provided {self.previous_summary}. Please continue from that summary and integrate it with the new images."
                        })
                    
                    response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    temperature=0.3)

                    self.previous_summary += response.choices[0].message.content
                    self.final_summary = response.choices[0].message.content

                    
                except Exception as e:
                    logging.error(f"Error calling OpenAI for GUID {guid}: {e}")

        finalSummary = self.get_final_summary(self.previous_summary)
        return finalSummary if finalSummary else self.previous_summary
    



        
