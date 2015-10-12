#! /usr/local/bin/python3

# import class and constants
import cgi
import urllib

# jinja2
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader("templates"))

from discoursesso import DiscourseSSO
from ldap3 import Server, Connection, ALL, AUTH_SIMPLE, SUBTREE


def validate_user_ldap_details(username, password):
    ldap_server="ldap://ldap.mycompany.com"
    base_dn = "ou=People,dc=mycompany,dc=com"
    user_dn = "uid="+username+","+ base_dn

    err_obj = {"status": "FAIL", "email": "", "external_id": "", "name": "", "username": ""} 

    # define the server
    s = Server(ldap_server, get_info=ALL)  # define an unsecure LDAP server, requesting info on DSE and schema

    # define the connection
    c = Connection(s, user=user_dn, password=password, authentication=AUTH_SIMPLE, read_only=True)

    # perform the Bind operation
    if not c.bind():
        c.unbind()
        return err_obj
    else:
        # Get user details
        c.search(search_base = base_dn,
                 search_filter = '(&(uid='+username+')(objectClass=inetOrgPerson))',
                 search_scope = SUBTREE,
                 attributes = ['cn', 'mail'],
                 paged_size = 1)

        # Check if we have valid response
        response = c.response
        if len(response) < 1:
            return err_obj

        response = response[0]
        if "attributes" not in response or "cn" not in response["attributes"] or len(response["attributes"]["cn"]) < 1:
            return err_obj

        if "attributes" not in response or "mail" not in response["attributes"] or len(response["attributes"]["mail"]) < 1:
            return err_obj

        name = response["attributes"]["cn"][0]
        email = response["attributes"]["mail"][0]
        return {"status": "OK", "email": email, "external_id": username, "name": name, "username": username}

def render_html(template, args={}):
    print('Content-type: text/html\n\n')
    print(template.render(args))

def redirect_url(url):
    render_html(env.get_template("redirect.html"), args={"url": url})

def handle_request():
    secret_key = "MY_SECRET_KEY_GENERATED_FROM_DISCOURSE_ADMIN_SETTINGS_PAGE"

    form = cgi.FieldStorage()
    if "sso" not in form or "sig" not in form:
        render_html(env.get_template("sso_error.html"))
        return

    if "encoded" in form:
        payload = form["sso"].value
        sig = form["sig"].value
    else:
        payload = urllib.parse.quote_plus(form["sso"].value)
        sig = urllib.parse.quote_plus(form["sig"].value)

    sso = DiscourseSSO(secret_key)
    if not sso.validate(payload, sig):
        render_html(env.get_template("sso_error.html"))
        return

    if "username" not in form or "password" not in form:
        render_html(env.get_template("login.html"), args={"sso": payload, "sig": sig})
        return

    username = form["username"].value
    password = form["password"].value

    result = validate_user_ldap_details(username, password)
    if result["status"]  == "FAIL":
        render_html(env.get_template("login.html"), args={"sso": payload, "sig": sig, "error": "Invalid LDAP username or password"})
        return

    nonce = sso.get_nonce(payload)
    min_req_credentials = {
        "external_id": result["external_id"],
        "nonce": nonce,
        "email": result["email"],
        "name": result["name"],
        "username": result["username"]
    }
    url = "https://forums.dev.mycompany.com/session/sso_login?%s" % sso.build_login_URL(min_req_credentials)
    redirect_url(url)

if __name__ == "__main__":
    try:
        handle_request()
    except Exception as e:
        render_html(env.get_template("sso_error.html"))
