import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="URL Shortener Dashboard", page_icon="🔗", layout="centered")

# Store the JWT login token in Streamlit's session state
if "token" not in st.session_state:
    st.session_state.token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

st.title("🔗 URL Shortener & Analytics")

# --- VIEW 1: LOGIN & REGISTER SCREEN ---
if st.session_state.token is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        st.subheader("Sign in to your account")
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", type="primary"):
            response = requests.post(
                f"{API_URL}/login",
                data={"username": login_email, "password": login_password}
            )
            if response.status_code == 200:
                st.session_state.token = response.json()["access_token"]
                st.session_state.user_email = login_email
                st.rerun()
            else:
                st.error("Invalid email or password.")

    with tab2:
        st.subheader("Create a new account")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        
        if st.button("Register"):
            response = requests.post(
                f"{API_URL}/register",
                json={"email": reg_email, "password": reg_password}
            )
            if response.status_code == 201:
                st.success("Account created! Switch to the Login tab to sign in.")
            else:
                st.error(response.json().get("detail", "Registration failed."))

# --- VIEW 2: LOGGED-IN CRUD DASHBOARD ---
else:
    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    # Top bar with user info and Logout button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.write(f"Logged in as **{st.session_state.user_email}**")
    with col2:
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.user_email = ""
            st.rerun()

    st.divider()

    # 1. CREATE SHORT LINK
    st.subheader("Create a New Short Link")
    with st.form("create_link_form", clear_on_submit=True):
        long_url = st.text_input("Paste your long URL (e.g., https://python.org)")
        submitted = st.form_submit_button("Shorten URL", type="primary")
        
        if submitted and long_url:
            res = requests.post(f"{API_URL}/links", json={"original_url": long_url}, headers=headers)
            if res.status_code == 201:
                short_url = res.json()["short_url"]
                st.success(f"Short link created: **{short_url}**")
            elif res.status_code == 401:
                st.session_state.token = None
                st.rerun()
            else:
                st.error("Failed to create link.")

    st.divider()

    # 2. READ, UPDATE & DELETE LINKS
    st.subheader("Your Shortened Links & Click Analytics")
    res = requests.get(f"{API_URL}/links", headers=headers)

    if res.status_code == 200:
        links = res.json().get("links", [])
        if not links:
            st.info("No links created yet. Paste a URL above to create your first one!")
        else:
            for link in links:
                short_code = link["short_code"]
                short_url = f"{API_URL}/{short_code}"
                status_badge = "🟢 Active" if link["is_active"] else "🔴 Paused"

                with st.expander(f"**{short_code}** — {link['total_clicks']} Clicks ({status_badge})"):
                    st.markdown(f"**Short URL:** [{short_url}]({short_url})")
                    st.write(f"**Destination:** {link['original_url']}")
                    
                    # Update Form
                    new_url = st.text_input("Update Destination URL", value=link["original_url"], key=f"url_{short_code}")
                    is_active = st.checkbox("Link Active", value=bool(link["is_active"]), key=f"active_{short_code}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Save Changes", key=f"save_{short_code}"):
                            upd = requests.put(
                                f"{API_URL}/links/{short_code}",
                                json={"original_url": new_url, "is_active": is_active},
                                headers=headers
                            )
                            if upd.status_code == 200:
                                st.success("Updated!")
                                st.rerun()
                    with btn_col2:
                        if st.button("Delete Link", key=f"del_{short_code}"):
                            dele = requests.delete(f"{API_URL}/links/{short_code}", headers=headers)
                            if dele.status_code == 200:
                                st.warning("Deleted!")
                                st.rerun()
    elif res.status_code == 401:
        st.session_state.token = None
        st.rerun()
