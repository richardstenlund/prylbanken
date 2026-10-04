import base64
import io
import json
import socket
import struct
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

import linkcheck
import test_server as integration


class RegistryTests(unittest.TestCase):
    setUpClass = integration.ServerTests.__dict__["setUpClass"]
    tearDownClass = integration.ServerTests.__dict__["tearDownClass"]
    start = integration.ServerTests.__dict__["start"]
    request = integration.ServerTests.__dict__["request"]
    setUp = integration.ServerTests.setUp
    create = integration.ServerTests.create

    def server(self, name="VPN host"):
        status, result, _ = self.request("POST", "/api/servers",
            {"name":name,"address":"192.168.1.10","os":"Debian","role":"Games",
             "url":"https://192.168.1.10:8006","notes":"Internal"})
        self.assertEqual(status, 201, result)
        return result["id"]

    def reader(self, role="reader"):
        self.request("POST", "/api/users", {"username":"limited","password":"reader-test-password","role":role})
        status, _, headers = self.request("POST", "/api/login",
            {"username":"limited","password":"reader-test-password"}, auth=False)
        self.assertEqual(status,200)
        type(self).cookie = headers["Set-Cookie"].split(";",1)[0]
        type(self).csrf = self.request("GET","/api/me")[1]["csrf"]

    def test_server_crud_item_and_guide_associations_history_and_delete(self):
        server = self.server()
        item = self.create(server_ids=[server], entry_type="troubleshooting",symptoms="Steam fails",
                           solution="Check disk",incident_at="2026-10-04",pinned="1",language="markdown")
        guide = self.request("POST","/api/guides",{"title":"Server guide","steps":[{"text":"Check"}],"server_ids":[server]})[1]["id"]
        row = self.request("GET","/api/items")[1][0]
        self.assertEqual(row["server_ids"],[server])
        self.assertEqual(row["symptoms"],"Steam fails")
        self.assertEqual(row["pinned"],"1")
        self.assertEqual(self.request("PUT",f"/api/items/{item}",{**row,"server_ids":[99999]})[0],400)
        self.assertEqual(self.request("POST","/api/servers",{"name":"bad","url":"javascript:alert(1)"})[0],400)
        self.assertEqual(self.request("POST","/api/servers",{"name":"bad","url":"https://user:pass@example.com"})[0],400)
        self.assertEqual(self.request("PUT",f"/api/servers/{server}",{"name":"Updated"})[0],200)
        self.assertEqual(self.request("GET","/api/servers")[1][0]["name"],"Updated")
        self.assertEqual(self.request("DELETE",f"/api/servers/{server}")[0],200)
        self.assertEqual(self.request("GET","/api/items")[1][0]["server_ids"],[])
        self.assertEqual(self.request("GET","/api/guides")[1][0]["server_ids"],[])
        history = self.request("GET",f"/api/items/{item}/history")[1]
        self.assertGreaterEqual(len(history),2)
        oldest = history[-1]
        self.assertEqual(self.request("POST",f'/api/items/{item}/history/{oldest["id"]}/restore')[0],200)
        self.assertEqual(self.request("GET","/api/items")[1][0]["server_ids"],[])
        self.assertEqual(self.request("GET","/api/guides")[1][0]["id"],guide)
        new_server=self.server()
        self.assertGreater(new_server,server)

    def test_profiles_reject_secret_names_and_keep_literal_values(self):
        payload={"name":"Home","description":"No secrets","variables":{"ip":"192.168.1.10","port":"27015","server_path":"C:\\Games\\$&"}}
        status,result,_=self.request("POST","/api/profiles",payload)
        self.assertEqual(status,201,result)
        row=self.request("GET","/api/profiles")[1][0]
        self.assertEqual(row["variables"],payload["variables"])
        for variables in ({},{"password":"x"},{"api_key":"x"},{"myTOKEN":"x"},{"bad-name":"x"},{"ip":123},{"ip":""},
                          {f"value_{i}":"x" for i in range(51)}):
            self.assertEqual(self.request("POST","/api/profiles",{**payload,"variables":variables})[0],400)
        self.assertEqual(self.request("DELETE",f'/api/profiles/{result["id"]}')[0],200)

    def test_saved_filters_and_guide_progress_on_server_change(self):
        first,second=self.server("First"),self.server("Second")
        filters={"server":str(first),"troubleshooting":True}
        status,result,_=self.request("POST","/api/searches",{"name":"Server errors","filters":filters})
        self.assertEqual(status,201,result)
        saved=self.request("GET","/api/searches")[1][0]["filters"]
        self.assertEqual(saved["server"],str(first));self.assertTrue(saved["troubleshooting"])
        for invalid in ({"server":12},{"server":"abc"},{"troubleshooting":"true"}):
            self.assertEqual(self.request("POST","/api/searches",{"name":"Invalid","filters":invalid})[0],400)
        guide=self.request("POST","/api/guides",{"title":"Test","steps":[{"text":"Check"}],"server_ids":[first]})[1]["id"]
        row=self.request("GET","/api/guides")[1][0]
        key=row["steps"][0]["key"]
        self.assertEqual(self.request("PUT",f"/api/guides/{guide}/progress",{"completed":[key]})[0],200)
        row["server_ids"]=[second]
        self.assertEqual(self.request("PUT",f"/api/guides/{guide}",row)[0],200)
        row=self.request("GET","/api/guides")[1][0]
        self.assertEqual(row["completed"],[])
        key=row["steps"][0]["key"]
        self.request("PUT",f"/api/guides/{guide}/progress",{"completed":[key]})
        self.request("DELETE",f"/api/servers/{second}")
        self.assertEqual(self.request("GET","/api/guides")[1][0]["completed"],[])

    def test_duplicate_preserves_payload_without_marker_pin_or_history(self):
        server=self.server()
        original=self.create(content="  echo {{ip}}\n",pinned="1",favorite=True,server_ids=[server],
                             filename="test.bin",filedata=base64.b64encode(b"\0data").decode(),risk="change")
        status,result,_=self.request("POST",f"/api/items/{original}/duplicate",{})
        self.assertEqual(status,201,result)
        rows={row["id"]:row for row in self.request("GET","/api/items")[1]}
        copy=rows[result["id"]]
        self.assertEqual(copy["content"],"  echo {{ip}}\n")
        self.assertEqual(copy["server_ids"],[server])
        self.assertEqual(copy["pinned"],"0")
        self.assertEqual(copy["favorite"],0)
        self.assertEqual(rows[original]["pinned"],"1")
        self.assertEqual(self.request("GET",f'/api/files/{copy["id"]}')[1],b"\0data")
        self.assertEqual(len(self.request("GET",f'/api/items/{copy["id"]}/history')[1]),1)
        self.assertEqual(self.request("POST","/api/items/999999/duplicate",{})[0],404)

    def test_reader_roles_and_editor_pin_guard(self):
        server=self.server()
        item=self.create(pinned="1")
        admin_cookie,admin_csrf=type(self).cookie,type(self).csrf
        self.reader()
        for path in ("/api/servers","/api/profiles"):
            self.assertEqual(self.request("GET",path)[0],200)
            self.assertEqual(self.request("POST",path,{})[0],403)
        for path in ("/api/bookmarks/preview",f"/api/items/{item}/duplicate",f"/api/items/{item}/check-link"):
            self.assertEqual(self.request("POST",path,{})[0],403)
        self.assertEqual(self.request("GET","/api/storage")[0],403)
        type(self).cookie,type(self).csrf=admin_cookie,admin_csrf
        self.request("PUT","/api/users/2",{"role":"editor"})
        headers=self.request("POST","/api/login",{"username":"limited","password":"reader-test-password"},auth=False)[2]
        type(self).cookie=headers["Set-Cookie"].split(";",1)[0];type(self).csrf=self.request("GET","/api/me")[1]["csrf"]
        row=self.request("GET","/api/items")[1][0]
        self.assertEqual(self.request("PUT",f"/api/items/{item}",{**row,"pinned":"0"})[0],400)
        self.assertEqual(self.request("PUT",f"/api/items/{item}",{**row,"content":"edited"})[0],200)
        self.assertEqual(self.request("POST","/api/items",{"title":"pin","category":"kod","pinned":"1"})[0],400)
        self.assertEqual(self.request("POST",f"/api/items/{item}/duplicate",{})[0],201)

    def test_bookmark_preview_safety_import_duplicate_and_limits(self):
        html='<DL><DT><A HREF="https://example.com/a?x=1&amp;y=2">Example &lt;img&gt;</A>' \
             '<A HREF="javascript:alert(1)">Bad</A><A HREF="file:///etc/passwd">Bad</A>' \
             '<A HREF="https://user:pass@example.com">Bad</A><script>alert(1)</script></DL>'
        status,result,_=self.request("POST","/api/bookmarks/preview",{"html":html})
        self.assertEqual(status,200,result)
        self.assertEqual(result["skipped"],3)
        self.assertEqual(result["items"][0]["title"],"Example <img>")
        self.assertEqual(result["items"][0]["content"],"https://example.com/a?x=1&y=2")
        payload={"items":result["items"],"allow_duplicates":False}
        self.assertEqual(self.request("POST","/api/batch/import",payload)[1]["added"],1)
        self.assertEqual(self.request("POST","/api/batch/import",payload)[1]["skipped"],1)
        self.assertEqual(self.request("POST","/api/bookmarks/preview",{"html":"x"*(2*1024*1024)})[0],200)
        self.assertEqual(self.request("POST","/api/bookmarks/preview",{"html":"x"*(2*1024*1024+1)})[0],400)
        self.assertEqual(self.request("POST","/api/bookmarks/preview",
            {"html":'<a href="https://example.com">A</a>'*5001})[0],400)

    def test_json_zip_roundtrip_registry_associations_and_storage(self):
        server=self.server()
        self.request("POST","/api/profiles",{"name":"Home","variables":{"ip":"192.168.1.10"}})
        project=self.request("POST","/api/projects",{"name":"Test"})[1]["id"]
        item=self.create(project_ids=[project],server_ids=[server],symptoms="Error",entry_type="troubleshooting",
                         filename="x.bin",filedata=base64.b64encode(b"12345").decode())
        self.request("POST","/api/guides",{"title":"Guide","steps":[{"text":"X","item_id":item}],"server_ids":[server]})
        backup=self.request("GET","/api/backup")[1]
        self.assertEqual(backup["guides"][0]["server_ids"],[server])
        self.assertEqual(backup["profiles"][0]["variables"],{"ip":"192.168.1.10"})
        self.assertEqual(self.request("POST","/api/restore",backup)[0],201)
        copies=self.request("GET","/api/items")[1]
        copied=next(row for row in copies if row["id"]!=item)
        self.assertNotEqual(copied["server_ids"],[server])
        self.assertEqual(copied["symptoms"],"Error")
        with zipfile.ZipFile(io.BytesIO(self.request("GET",f"/api/projects/{project}/export")[1])) as zipped:
            exported=json.loads(zipped.read("library.json"))
            self.assertEqual(exported["servers"][0]["id"],server)
            self.assertEqual(exported["items"][0]["server_ids"],[server])
        status,state,_=self.request("GET","/api/storage")
        self.assertEqual(status,200,state)
        self.assertEqual(state["attachment_bytes"],10)
        self.assertEqual(state["attachment_count"],2)
        self.assertEqual(state["largest"][0]["bytes"],5)
        self.assertGreater(state["database_bytes"],0)
        self.assertIn("backups",state)

    def test_links_opt_in_private_addresses_never_reached_and_rate_limits(self):
        item=self.create(category="lankar",content="http://127.0.0.1/")
        self.assertEqual(self.request("POST",f"/api/items/{item}/check-link",{})[0],400)
        self.assertEqual(self.request("PUT","/api/settings",{"link_check_enabled":True})[0],200)
        self.assertTrue(self.request("GET","/api/settings")[1]["registration_open"])
        for _ in range(10):
            status,result,_=self.request("POST",f"/api/items/{item}/check-link",{})
            self.assertEqual(status,400,result)
            self.assertIn("nekas",result["error"])
        self.assertEqual(self.request("POST",f"/api/items/{item}/check-link",{})[0],429)
        checks=self.request("GET","/api/link-checks")[1]
        self.assertEqual(checks[0]["status"],"blocked-or-error")
        row=self.request("GET","/api/items")[1][0]
        self.request("PUT",f"/api/items/{item}",{**row,"content":"https://example.com/"})
        self.assertEqual(self.request("GET","/api/link-checks")[1],[])

    def test_pwa_assets_have_correct_shapes_and_no_authenticated_cache(self):
        manifest=json.loads(self.request("GET","/manifest.webmanifest",auth=False)[1])
        self.assertEqual(manifest["start_url"],"/")
        self.assertEqual(manifest["display"],"standalone")
        for size in (192,512):
            status,png,headers=self.request("GET",f"/icon-{size}.png",auth=False)
            self.assertEqual(status,200)
            self.assertEqual(headers.get_content_type(),"image/png")
            self.assertEqual(struct.unpack(">II",png[16:24]),(size,size))
        worker=self.request("GET","/service-worker.js",auth=False)[1].decode()
        self.assertNotIn('addEventListener("fetch"',worker)
        self.assertNotIn("caches.",worker)
        self.assertNotIn("localStorage",worker)
        self.assertEqual(self.request("GET","/expansion.js",auth=False)[0],200)


class PublicLinkTests(unittest.TestCase):
    def test_addresses_are_public_only(self):
        for address in ("127.0.0.1","10.0.0.1","192.168.1.1","169.254.169.254","100.64.0.1",
                        "::1","fc00::1","fe80::1","::ffff:8.8.8.8","2002:0808:0808::1","224.0.0.1",
                        "168.63.129.16","192.0.2.1"):
            self.assertFalse(linkcheck.public_address(address),address)
        self.assertTrue(linkcheck.public_address("8.8.8.8"))
        self.assertTrue(linkcheck.public_address("2606:4700:4700::1111"))

    def test_url_validation_mixed_dns_and_dns_rebinding_pin(self):
        for url in ("ftp://example.com","http://user:pass@example.com","http://example.com:8006","http://example.com/\n",
                    "http://example.com\\@127.0.0.1/"):
            with self.assertRaises(ValueError):
                linkcheck.endpoint(url,time.monotonic()+8)
        infos=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("8.8.8.8",443)),
               (socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",443))]
        with patch.object(linkcheck.socket,"getaddrinfo",return_value=infos):
            with self.assertRaises(ValueError):
                linkcheck.endpoint("https://example.com",time.monotonic()+8)
        with patch.object(linkcheck.socket,"getaddrinfo",return_value=infos[:1]):
            parsed,host,port,info=linkcheck.endpoint("https://example.com",time.monotonic()+8)
            self.assertEqual(info[4],("8.8.8.8",443))
            self.assertEqual(host,"example.com")

    def test_redirect_internal_host_blocked_and_public_status_classified(self):
        public=(socket.AF_INET,socket.SOCK_STREAM,6,"",("8.8.8.8",80))
        private=(socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",80))
        connection=Mock()
        response=Mock(status=302);response.getheader.return_value="http://127.0.0.1/"
        connection.getresponse.return_value=response
        with patch.object(linkcheck.socket,"getaddrinfo",side_effect=[[public],[private]]), \
             patch.object(linkcheck.http.client,"HTTPConnection",return_value=connection) as factory:
            with self.assertRaises(ValueError):
                linkcheck.check("http://example.com")
            self.assertEqual(factory.call_count,1)
            self.assertEqual(connection.request.call_args.args[0],"HEAD")
            self.assertNotIn("Cookie",connection.request.call_args.kwargs["headers"])
        connection=Mock();response=Mock(status=404);response.getheader.return_value=None;connection.getresponse.return_value=response
        with patch.object(linkcheck.socket,"getaddrinfo",return_value=[public]), \
             patch.object(linkcheck.http.client,"HTTPConnection",return_value=connection), \
             patch.object(linkcheck.socket,"socket") as socket_factory:
            result=linkcheck.check("http://example.com")
            self.assertEqual(result["status"],"http-error")
            connection._create_connection(("evil-rebind.invalid",80),1)
            socket_factory.return_value.connect.assert_called_once_with(("8.8.8.8",80))

    def test_deadline_reader_cannot_be_kept_alive_by_slow_headers(self):
        reader=linkcheck.DeadlineReader(Mock(),time.monotonic()-1)
        with self.assertRaises(TimeoutError):
            reader.readinto(bytearray(1))

    def test_real_http_parser_and_socket_share_a_total_deadline(self):
        client,server=socket.socketpair()
        wrapped=linkcheck.DeadlineSocket(client,time.monotonic()+1)
        try:
            wrapped.sendall(b"HEAD / HTTP/1.1\r\n\r\n")
            self.assertEqual(server.recv(1024),b"HEAD / HTTP/1.1\r\n\r\n")
            server.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
            response=linkcheck.http.client.HTTPResponse(wrapped,method="HEAD")
            response.begin()
            self.assertEqual(response.status,200)
            self.assertEqual(response.read(),b"")
            response.close()
            wrapped.deadline=time.monotonic()-1
            with self.assertRaises(TimeoutError):
                wrapped.sendall(b"x")
        finally:
            wrapped.close();server.close()
