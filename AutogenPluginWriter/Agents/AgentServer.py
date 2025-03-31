from flask import Flask, request, jsonify

from DevOpsAgentForce import DevOpsAgentForce

app = Flask(__name__)

@app.route('/trigger', methods=['POST', 'GET'])
def trigger_agent():
    try:
        if request.method == 'GET':
            user_input = request.args.get('input')
            if not user_input:
                return jsonify({"message": "Provide 'input' as a query parameter"}), 200

        #user_input = request.json.get('input') if request.is_json else None
        
        
        # Call DevOpsAgent1 with the user input
        agent = DevOpsAgentForce()
        user_query = user_input
        response = agent.process_query(user_query)
        return f"<html><body><h1>Response</h1><p>{response}</p></body></html>", 200, {'Content-Type': 'text/html'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)