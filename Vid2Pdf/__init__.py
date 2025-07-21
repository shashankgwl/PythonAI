import azure.functions as func
import logging
from azure.storage.blob import BlobServiceClient
import os
import openai
import uuid
from PIL import Image
import io
from Vid2Pdf.LLMBlobHelper import LLMBlobHelper


app = func.FunctionApp()
connection_string = os.environ.get("AzureVideoStorage")
logging.info(f"Using connection string: {connection_string}")
folderGUID = str(uuid.uuid4())
tmp_folder = "/tmp"
localVideoPath = tmp_folder + "/" + folderGUID
localFramesPath = localVideoPath + "/frames"
videoFile = "/video.mp4"
ffmpeg_path = os.path.join(os.getcwd(), 'Vid2Pdf', 'ffmpeg', 'ffmpeg.run') # Adjust the path as necessary
audiotext =''
# client = AzureOpenAI(
#     api_version="2024-12-01-preview",
#     azure_endpoint= os.environ.get("AifEndPoint") ,
#     api_key= os.environ.get("AifApiKey"),
# )


def main(inputBlob: func.InputStream):
    # Check if the blob trigger event is a delete operation
    if inputBlob.length is None or inputBlob.length == 0 or not inputBlob.name.lower().endswith('.mp4'):
        return

    logging.info(f"Python blob trigger entered successfully"
                f"Name: {inputBlob.name}"
                f"Blob Size: {inputBlob.length} bytes")
    folder = inputBlob.name.split('/')[1]
    logging.info(f"Calling checkFFMPEG() to set permissions for ffmpeg")
    checkPath(ffmpeg_path)

    #creating frames in tmp folder
    if(checkPath(tmp_folder)) :
        logging.info(f"Temporary folder exists at {tmp_folder}.")
        #delete everything in the tmp folder
        logging.info(f"Deleting all files in the temporary folder: {tmp_folder}")
        DeleteFromTmp(tmp_folder)

        #first create localVideoPath
        logging.info(f"creating local video path: {localVideoPath}")

        if not os.path.exists(localVideoPath):
            try:
                os.makedirs(localVideoPath)
                logging.info(f"Local video path folder created at {localVideoPath}.")
            except Exception as e:
                logging.error(f"Local video path folder : {e}")
                return

        # create a frames folder inside localVideoPath
        
        logging.info(f"Downloading video to local path: {localVideoPath+videoFile}")
        try:
            with open(localVideoPath+videoFile, "wb") as video_file:
                video_file.write(inputBlob.read())
            logging.info(f"Video downloaded successfully to {localVideoPath}.mp4")
        except Exception as e:
            logging.error(f"Error creating temporary folder: {e}")
            return
        
        # now extracting frames from the video
        logging.info(f"Calling ExecuteFfmpeg() to extract KEY frames from the video")
        ExecuteFfmpeg(ffmpeg_path, localVideoPath)
    else:
        logging.error(f"Temporary folder does not exist at {tmp_folder}.")
        return


    createFolderInContainer("videos", folder)
    #now reading the frames from the tmp folder and uploading them to the container
    logging.info(f"Uploading frames to the folder: {folder}")
    UploadFramesToBlob(folder, localVideoPath)
    logging.info(f"Uploading frames to blob done. Now extracting audio from the video using FFMPEG")
    ExtractAudioUsingFfmpeg(folder, localVideoPath)
    logging.info(f"Audio extracted and uploaded to blob storage. Now converting JPGs to base64 and calling AI function")
    helper = LLMBlobHelper(
    connection_string = connection_string,
    container_name="videos",
    logging=logging)
    # Convert all JPGs to base64
    logging.info(f"Converting all JPGs to base64")
    blob64 = helper.convert_all_jpgs(folder)
    logging.info(f"Converted JPGs to base64. Now calling AI function to summarize the images and audio transcription")
    final_summary = helper.call_aif(blob64, batchsize=5, mp4_folder=folder, guid_file=folderGUID)
    logging.info(f"AI function called successfully. Final summary: {final_summary}")
    if final_summary:
        logging.info(f"Final summary: {final_summary}")
        create_final_smmary_in_blob_fromhtml(final_summary, folder, folderGUID)
    else:
        logging.error(f"Final summary is empty. AI function might have failed or returned no summary.")


def create_final_smmary_in_blob_fromhtml(final_summary, folder_path, guid_path):
    """
    Create a final summary in HTML format and upload it to the blob storage.
    """
    logging.info(f"Creating final summary in HTML format")
    html_content = f"""
    <html>
        <head>
            <title>Video Summary</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    color: #333;
                    background-color: #f4f4f4;
                    padding: 20px;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.5;
                }}
            </style>
        </head>
        <body>
            <h1>Video Summary</h1>
            <p>{final_summary}</p>
        </body>
    </html>
    """
    
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client("videos")
    
    blob_name = f"{folder_path}/{guid_path}/final_summary.html"
    blob_client = container_client.get_blob_client(blob_name)
    
    try:
        blob_client.upload_blob(html_content, overwrite=True)
        logging.info(f"Final summary uploaded to blob storage at {blob_name}")
    except Exception as e:
        logging.error(f"Error uploading final summary to blob storage: {e}")



def ExtractAudioUsingFfmpeg(folder, localVideoPath):
    logging.info(f"Extracting audio from the video using FFMPEG")
    audio_file_path = os.path.join(localVideoPath, os.environ.get("Mp3FileName"))
    command = f'{ffmpeg_path} -i {localVideoPath+videoFile} -q:a 0 -map a {audio_file_path}'
    logging.info(f"FFMPEG command for audio extraction: {command}")
    
    try:
        os.system(command)
        logging.info("Audio extracted successfully.")
        
        # Upload the audio file to the blob storage
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client("videos")
        blob_client = container_client.get_blob_client(f"{folder}/{folderGUID}/{os.environ.get('Mp3FileName')}")
        
        with open(audio_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
            logging.info(f"Uploaded audio.mp3 to container {folder}/{folderGUID}")
            #extract the text from the audio file using OpenAI
            logging.info(f"Extracting text from the audio file using OpenAI")
            openai.api_key = os.environ.get("OpenAIKey") 
            audioText = openai.audio.transcriptions.create(
                file=open(audio_file_path, "rb"),
                model="whisper-1",
                response_format="text"
            )
            logging.info(f"Upload audio text to blob storage")
            blob_client = container_client.get_blob_client(f"{folder}/{folderGUID}/audio_text.txt")
            blob_client.upload_blob(audioText, overwrite=True)
    except Exception as e:
        logging.error(f"Error extracting audio: {e}")



def UploadFramesToBlob(folder, localVideoPath):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client("videos")
    logging.info(f"now uploading file from path: {localVideoPath}")
    for filename in os.listdir(localVideoPath):
        if filename.lower().endswith('.jpg'):
            file_path = os.path.join(localVideoPath, filename)
            if os.path.isfile(file_path):
                blob_client = container_client.get_blob_client(f"{folder}/{folderGUID}/{filename}")
                logging.info(f"compressing the file: {file_path} before uploading blob storage")
                with Image.open(file_path) as img:
                    img_io = io.BytesIO()
                    img.save(img_io, format='JPEG', quality=75, optimize=True)
                    img_io.seek(0)  # Reset the stream position to the beginning
                    blob_client.upload_blob(img_io, overwrite=True)


def DeleteFromTmp(tmp_folder):
    import shutil
    for filename in os.listdir(tmp_folder):
        file_path = os.path.join(tmp_folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
                logging.info(f"Deleted file: {file_path}")
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                logging.info(f"Deleted directory: {file_path}")
        except Exception as e:
            logging.error(f"Failed to delete {file_path}. Reason: {e}")

def ExecuteFfmpeg(ffmpeg_path, localVideoPath):
    logging.info(f"Inside ExecuteFfmpeg to extract KEY frames from the video")
    command = f'{ffmpeg_path} -i "{localVideoPath+videoFile}" -vf "select=eq(pict_type\\,I)" -qscale:v 3 -vsync vfr "{localVideoPath}/frame_%04d.jpg"'
    #command = f'{ffmpeg_path} -i {localVideoPath+videoFile} -vf "select=eq(pict_type\\,I)" -vsync vfr {localVideoPath}/frame_%04d.png'
    logging.info(f"FFMPEG command: {command}")
    executeFFmpegCommand(command)

def executeFFmpegCommand(command: str):
    logging.info(f"Executing FFMPEG command: {command}")
    try:
        os.system(command)
        logging.info("FFMPEG command executed successfully.")
    except Exception as e:
        logging.error(f"Error executing FFMPEG command: {e}")

def checkPath(path: str) -> bool:
    logging.info(f"Checking if the file ffmpeg exists at {path}")
    if os.path.exists(path):
        logging.info(f"PATH exists at {path}. Setting permissions.")
        return True
    else:
        logging.error(f"ffmpeg not found at {path}.")
        return False

def createFolderInContainer(container_name: str, folder_name: str):

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)

    # Create a new blob with a trailing slash to represent a folder
    blob_client = container_client.get_blob_client(f"{folder_name}/")
    blob_client.upload_blob(b"", overwrite=True)
    
    logging.info(f"Folder '{folder_name}' created in container '{container_name}'.")