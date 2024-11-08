import os
import requests
import json
from requests_oauthlib import OAuth1
import re

def count_characters(text):
    return len(text)

def create_oauth():
    return OAuth1(
        client_key=os.environ.get('API_KEY'),
        client_secret=os.environ.get('API_KEY_SECRET'),
        resource_owner_key=os.environ.get('ACCESS_TOKEN'),
        resource_owner_secret=os.environ.get('ACCESS_TOKEN_SECRET')
    )

def fetch_full_wiki_content(title):
    base_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": title.replace(' ', '_'),
        "format": "json",
        "prop": "wikitext",
        "utf8": ""
    }

    full_text = ""
    continue_param = None
    while True:
        if continue_param:
            params['rvcontinue'] = continue_param
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if 'parse' in data and 'wikitext' in data['parse']:
            wikitext = data['parse']['wikitext']['*']
            text = re.sub(r'\{\{.+?\}\}|\[\[.+?\]\]|\[\[.+?\]\]|\&lt;ref.*?\&gt;.*?\<\/ref\>', '', wikitext)
            full_text += text + "\n"
        
        if 'continue' in data:
            continue_param = data['continue']['rvcontinue']
        else:
            break

    return full_text

def tweet(oauth, content, reply_to_id=None):
    url = "https://api.twitter.com/2/tweets"
    headers = {
        'Content-Type': 'application/json'
    }
    data = {'text': content}
    if reply_to_id:
        data['reply'] = {'in_reply_to_tweet_id': reply_to_id}

    try:
        response = requests.post(url, headers=headers, auth=oauth, json=data)
        response.raise_for_status()
        result = response.json()
        if 'data' in result:
            tweet_id = result['data']['id']
            author_id = result['data'].get('author_id', result.get('includes', {}).get('users', [{}])[0].get('id', None))
            if not author_id:
                print("Could not find author_id in the response.")
                return None
            return {
                'data': {
                    'id': tweet_id,
                    'author_id': author_id
                }
            }
        else:
            print("Unexpected response format from Twitter API:", result)
            return None
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        raise Exception(f"Tweet failed: {e}")

def summarize_with_gemini(text, gemini_api_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        "contents": [{
            "parts": [{
                "text": f"Summarize the following text in 1-5 tweets of 280 characters or less, separated by a newline character:\n\n{text}"
            }]
        }]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), params={'key': gemini_api_key})
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text'].split('\n')
    except requests.exceptions.HTTPError as e:
        print(f"Gemini API Error: {e.response.status_code} - {e.response.text}")
        raise Exception(f"Gemini summarization failed: {e}")

def main(args):
    print('Starting main function execution')

    wikipedia_url = 'https://en.wikipedia.org/api/rest_v1/page/random/summary'
    try:
        wiki_response = requests.get(wikipedia_url)
        wiki_response.raise_for_status()
        wiki_data = wiki_response.json()

        print('Wikipedia fetch successful')
        print(f"Title: {wiki_data['title']}")

        full_text = fetch_full_wiki_content(wiki_data['title'])

        print('Full Wikipedia Article Text:')
        print(full_text)

        if len(full_text) > 7000:
            full_text = full_text[:7000]

        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        summaries = summarize_with_gemini(full_text, gemini_api_key)

        print('Gemini summarization successful')

        oauth = create_oauth()
        first_tweet_text = f"{summaries[0]}\n{wiki_data['content_urls']['desktop']['page']}"
        result = tweet(oauth, first_tweet_text)
        if result:
            print('First tweet posted successfully')

            for summary in summaries[1:]:
                reply_to_id = result['data']['id']
                reply_text = f"@{result['data']['author_id']} {summary}"
                result = tweet(oauth, reply_text, reply_to_id)
                if result:
                    print('Reply tweet posted successfully')

        return {"body": "Tweet thread posted successfully!"}

    except requests.RequestException as e:
        print('Error:', str(e))
        return {"body": f'Error: {str(e)}'}
